# ab_core/dependency/inject.py

import inspect
from collections.abc import Callable
from contextlib import AsyncExitStack, ExitStack, asynccontextmanager, contextmanager
from functools import wraps
from inspect import isawaitable
from types import AsyncGeneratorType, GeneratorType
from typing import Annotated, Any, ParamSpec, TypeVar, get_args, get_origin, overload

from .depends import Depends

P = ParamSpec("P")
R = TypeVar("R")


# ---------- Wrap a single provider as a *sync* context manager ----------
@contextmanager
def _dep_to_cm(dep: Depends):
    obj = dep()  # value | awaitable | gen | async-gen
    # sync generator dep
    if isinstance(obj, GeneratorType):
        try:
            val = next(obj)
            yield val
            # normal completion: drive teardown path without GeneratorExit
            try:
                obj.send(None)
            except StopIteration:
                pass
        except BaseException as exc:
            # error path: propagate into generator for cleanup
            try:
                obj.throw(exc)
            except StopIteration:
                pass
            raise
        return

    # async generator dep (allowed in sync only if it yields a sync-safe value)
    if isinstance(obj, AsyncGeneratorType):
        raise RuntimeError("Async-generator dependency cannot be used in a sync context")

    # awaitable (not allowed in sync)
    if isawaitable(obj):
        raise RuntimeError("Awaitable dependency cannot be used in a sync context")

    # plain value
    try:
        yield obj
    finally:
        pass


# ---------- Wrap a single provider as an *async* context manager ----------
@asynccontextmanager
async def _dep_to_acm(dep: Depends):
    obj = dep()
    # async generator dep
    if isinstance(obj, AsyncGeneratorType):
        try:
            val = await obj.__anext__()
            yield val
            # normal completion: drive teardown path without GeneratorExit
            try:
                await obj.asend(None)
            except StopAsyncIteration:
                pass
        except BaseException as exc:
            try:
                await obj.athrow(exc)
            except StopAsyncIteration:
                pass
            raise
        return

    # sync generator dep (lift into async by using the sync CM inside)
    if isinstance(obj, GeneratorType):
        with _dep_to_cm(lambda: obj):  # reuse sync wrapper
            # re-call dep() would recreate the gen; wrap the *object* instead
            # so we need a lambda that returns the same generator object
            # NOTE: since we already have `obj` (the generator), this works.
            val = next(obj)  # consume here to get the value
            try:
                yield val
                try:
                    obj.send(None)
                except StopIteration:
                    pass
            except BaseException as exc:
                try:
                    obj.throw(exc)
                except StopIteration:
                    pass
                raise
        return

    # awaitable → value
    if isawaitable(obj):
        val = await obj  # type: ignore[func-returns-value]
        try:
            yield val
        finally:
            pass
        return

    # plain value
    try:
        yield obj
    finally:
        pass


# ---------- Resolve & enter all dependencies ----------
def _collect_dep_specs(sig: inspect.Signature):
    specs: list[tuple[str, Depends]] = []
    for name, param in sig.parameters.items():
        anno = param.annotation
        if get_origin(anno) is Annotated:
            _, *extras = get_args(anno)
            for e in extras:
                if isinstance(e, Depends):
                    specs.append((name, e))
                    break
    return specs


def _resolve_deps_sync(sig: inspect.Signature, bound: inspect.BoundArguments) -> ExitStack:
    stack = ExitStack()
    for name, dep in _collect_dep_specs(sig):
        if name in bound.arguments:
            continue
        val = stack.enter_context(_dep_to_cm(dep))
        bound.arguments[name] = val
    return stack


async def _resolve_deps_async(sig: inspect.Signature, bound: inspect.BoundArguments) -> AsyncExitStack:
    astack = AsyncExitStack()
    await astack.enter_async_context(_AsyncDepsBinder(astack, sig, bound))
    return astack


# ---- class-only resolver: plain value (no awaitables, no (a)generators)
def _resolve_class_dep_value(dep) -> Any:
    val = dep()  # let Depends handle persist/cache
    if isawaitable(val) or isinstance(val, (GeneratorType, AsyncGeneratorType)):
        raise RuntimeError("Class DI expects a plain value (no awaitables/(a)generators)")
    return val


class _AsyncDepsBinder:
    """Helper to enter all async dep contexts under a single AsyncExitStack."""

    def __init__(self, astack: AsyncExitStack, sig: inspect.Signature, bound: inspect.BoundArguments):
        self.astack = astack
        self.sig = sig
        self.bound = bound

    async def __aenter__(self):
        for name, dep in _collect_dep_specs(self.sig):
            if name in self.bound.arguments:
                continue
            val = await self.astack.enter_async_context(_dep_to_acm(dep))
            self.bound.arguments[name] = val
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # AsyncExitStack handles exit of all entered contexts.
        return False


# ---------- Decorator ----------
@overload
def inject(__fn: Callable[P, R]) -> Callable[P, R]: ...
@overload
def inject() -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def inject(target: Callable[..., Any] | type | None = None):
    def _wrap_fn(fn: Callable[P, R]) -> Callable[P, R]:
        sig = inspect.signature(fn)
        is_coro = inspect.iscoroutinefunction(fn)
        is_gen = inspect.isgeneratorfunction(fn)
        is_async_gen = inspect.isasyncgenfunction(fn)

        # Sync function
        if not (is_coro or is_gen or is_async_gen):

            @wraps(fn)
            def wrapper(*args: P.args, **kw: P.kwargs):
                bound = sig.bind_partial(*args, **kw)
                with _resolve_deps_sync(sig, bound):
                    return fn(**bound.arguments)  # type: ignore[arg-type]

            return wrapper  # type: ignore[return-value]

        # Coroutine
        if is_coro:

            @wraps(fn)
            async def wrapper(*args: P.args, **kw: P.kwargs):
                bound = sig.bind_partial(*args, **kw)
                async with await _resolve_deps_async(sig, bound):
                    return await fn(**bound.arguments)  # type: ignore[arg-type]

            return wrapper  # type: ignore[return-value]

        # Sync generator (proxy; *forward* throw into inner gen)
        if is_gen:

            @wraps(fn)
            def wrapper(*args: P.args, **kw: P.kwargs):
                bound = sig.bind_partial(*args, **kw)
                with _resolve_deps_sync(sig, bound):
                    gen = fn(**bound.arguments)
                    try:
                        while True:
                            try:
                                item = next(gen)
                            except StopIteration:
                                break
                            try:
                                yield item
                            except BaseException as thrown:
                                try:
                                    gen.throw(thrown)
                                except StopIteration:
                                    break
                                else:
                                    continue
                    finally:
                        try:
                            gen.close()
                        except Exception:
                            pass

            return wrapper  # type: ignore[return-value]

        # Async generator (proxy; *forward* athrow into inner agen)
        if is_async_gen:

            @wraps(fn)
            async def wrapper(*args: P.args, **kw: P.kwargs):
                bound = sig.bind_partial(*args, **kw)
                async with await _resolve_deps_async(sig, bound):
                    agen = fn(**bound.arguments)

                    try:
                        while True:
                            # pull next item manually
                            try:
                                item = await agen.__anext__()
                            except StopAsyncIteration:
                                break

                            # yield to caller, but forward thrown exceptions to inner agen
                            try:
                                yield item
                            except BaseException as thrown:
                                try:
                                    await agen.athrow(thrown)
                                except StopAsyncIteration:
                                    # inner agen handled it and finished
                                    break
                                else:
                                    # inner agen yielded a value after handling; continue loop
                                    continue
                    finally:
                        # ensure the inner generator is closed if not already
                        try:
                            await agen.aclose()
                        except Exception:
                            pass

            return wrapper  # type: ignore[return-value]

        return fn

    def _wrap_cls(cls: type) -> type:
        """Inject :class:`Depends` fields at construction."""
        orig_init = cls.__init__
        is_plain = orig_init is object.__init__

        # Optional: detect Pydantic BaseModel to pass kwargs instead of setattr
        try:
            from pydantic import BaseModel  # type: ignore

            is_pydantic = issubclass(cls, BaseModel)  # noqa: F821
        except Exception:
            is_pydantic = False

        @wraps(orig_init)
        def __init__(self, *args, **kwargs):  # type: ignore[no-self-use]
            injected: dict[str, Any] = {}

            for name, anno in getattr(cls, "__annotations__", {}).items():
                if name in kwargs:
                    continue
                if get_origin(anno) is Annotated:
                    _, *extras = get_args(anno)
                    for e in extras:
                        # Only resolve if not provided by caller
                        if isinstance(e, Depends):
                            injected[name] = _resolve_class_dep_value(e)
                            break

            if is_pydantic:
                # Pydantic must receive values via kwargs (no setattr before __init__)
                return orig_init(self, *args, **{**injected, **kwargs})

            if is_plain:
                # object.__init__ can't take kwargs; set attributes first
                for k, v in injected.items():
                    setattr(self, k, v)
                return orig_init(self)

            # Custom __init__: try kwargs first, fall back to setattr if signature rejects
            try:
                return orig_init(self, *args, **{**injected, **kwargs})
            except TypeError:
                for k, v in injected.items():
                    setattr(self, k, v)
                return orig_init(self, *args, **kwargs)

        cls.__init__ = __init__  # type: ignore[assignment]
        return cls

    def _apply(t):
        if inspect.isclass(t):
            return _wrap_cls(t)
        if callable(t):
            return _wrap_fn(t)  # type: ignore[arg-type]
        raise TypeError("@inject can only decorate a function or class")

    return _apply(target) if target is not None else _apply
