"""ab_core.dependency.inject
================================
Unified dependency-injection decorator that works for **plain functions**, **coroutines**,
**generators**, and **async-generators** as well as **classes**.  It mirrors the resource-cleanup
rules used by
`contextlib.ExitStack` *and* FastAPI’s own dependency system, so writing
and reasoning about resources feels completely familiar.

Bullet-point tour
-----------------
* **Single entry-point** - `@inject`.
* **Single start helper** - `_start_dep` starts a :class:`~ab_core.dependency.Depends` object and
returns *(value, finaliser)*.
* **Single finaliser runner** - `_finalise_sync` / `_finalise_async` imitate
  `ExitStack` exactly (truthy return ⇒ suppress).
* **Zero surprises** - a dependency generator that
  *catches* an injected exception swallows it; one that re-raises lets it
  bubble; a dependency can also suppress by returning ``True``.
* **FastAPI-aware** - because :class:`~ab_core.dependency.Depends` is a
  subclass of ``fastapi.Depends`` FastAPI recognises parameters marked
  with it as dependencies, not request-body fields.

The code is heavily documented; scroll down for implementation details.
"""

import inspect
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, ExitStack
from dataclasses import dataclass
from functools import wraps
from inspect import isawaitable
from types import AsyncGeneratorType, GeneratorType
from typing import (
    Annotated,
    Any,
    ParamSpec,
    TypeVar,
    get_args,
    get_origin,
    overload,
)

from .depends import Depends

P = ParamSpec("P")  # parameter pack for decorated callables
R = TypeVar("R")  # return-type variable


# -------------------------------------------------------------------- #
# 1.  Start a single dependency                                        #
# -------------------------------------------------------------------- #
@dataclass(slots=True)
class _StartedDep:
    """Return type of :func:`_start_dep`. Holds the injected *value* and a
    *finaliser* callable.  The finaliser accepts the current exception (or
    ``None``) and returns an *optional awaitable*.  Its **return value is used
    exactly like ``__exit__``: truthy ⇒ the exception is considered handled.
    """

    value: Any
    final: Callable[[BaseException | None], Awaitable[None] | None]


def _start_dep(dep: Depends, *, allow_async: bool) -> _StartedDep:
    """Instantiate *dep* and return the first value plus a finaliser.

    The function handles four kinds of loader outputs:

    1. **sync generator** - yield the first item, keep generator object
    2. **async generator** -                …
    3. **coroutine** - return coroutine object (await later)
    4. **plain value** - return it directly
    """
    obj = dep()  # may be value | coroutine | gen | async-gen

    # -- 1) Synchronous generator ----------------------------------
    if isinstance(obj, GeneratorType):
        try:
            value = next(obj)
        except StopIteration:  # pragma: no cover - degenerate loader
            raise RuntimeError("Generator dependency produced no value") from None

        def _final(exc: BaseException | None):
            try:
                if exc:
                    obj.throw(exc)
                else:
                    obj.close()
            except StopIteration:  # generator swallowed → suppress
                return bool(exc)
            return None  # propagate decision upwards

        return _StartedDep(value, _final)

    # -- 2) Asynchronous generator ---------------------------------
    if isinstance(obj, AsyncGeneratorType):

        async def _first():
            try:
                return await obj.__anext__()
            except StopAsyncIteration:
                raise RuntimeError("Async-generator produced no value") from None

        async def _final(exc: BaseException | None):
            try:
                if exc:
                    await obj.athrow(exc)
                else:
                    await obj.aclose()
            except StopAsyncIteration:
                return bool(exc)
            return None

        return _StartedDep(_first(), _final)

    # -- 3) Coroutine ----------------------------------------------
    if isawaitable(obj):
        if not allow_async:
            raise RuntimeError("Async dependency used inside a synchronous handler.")

        async def _noop(_: BaseException | None):
            return None

        return _StartedDep(obj, _noop)

    # -- 4) Plain value --------------------------------------------
    return _StartedDep(obj, lambda _: None)


# -------------------------------------------------------------------- #
# 2.  Bind *all* dependencies for a callable                           #
# -------------------------------------------------------------------- #


def _bind_all(
    sig: inspect.Signature,
    bound: inspect.BoundArguments,
    *,
    stack: ExitStack,
    astack: AsyncExitStack | None,
) -> list[Callable[[BaseException | None], Awaitable[None] | None]]:
    """Populate *bound* with values for every parameter annotated with
    :class:`Depends` and return their finalisers (LIFO order).
    """
    finals: list[Callable[[BaseException | None], Awaitable[None] | None]] = []

    for name, param in sig.parameters.items():
        if name in bound.arguments:
            continue  # caller supplied a value
        anno = param.annotation
        if get_origin(anno) is Annotated:
            _, *extras = get_args(anno)
            for extra in extras:
                if isinstance(extra, Depends):
                    started = _start_dep(extra, allow_async=astack is not None)
                    finals.append(started.final)
                    bound.arguments[name] = started.value
                    break
    return finals


# -------------------------------------------------------------------- #
# 3.  Finalise helpers     (mirror ExitStack exactly)                  #
# -------------------------------------------------------------------- #


def _finalise_sync(finals, exc: BaseException | None) -> None:
    for fin in reversed(finals):
        try:
            res = fin(exc)
        except BaseException as new_exc:
            exc = new_exc
        else:
            if exc is not None and bool(res):
                exc = None  # swallowed
        # continue loop with updated *exc*
    if exc is not None:
        raise exc


async def _finalise_async(finals, exc: BaseException | None) -> None:
    for fin in reversed(finals):
        try:
            res = fin(exc)
            if isawaitable(res):
                res = await res
        except BaseException as new_exc:
            exc = new_exc
        else:
            if exc is not None and bool(res):
                exc = None
    if exc is not None:
        raise exc


# -------------------------------------------------------------------- #
# 4.  @inject decorator implementation                                 #
# -------------------------------------------------------------------- #
@overload
def inject(__fn: Callable[P, R]) -> Callable[P, R]: ...


@overload
def inject() -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def inject(target: Callable[..., Any] | type | None = None):
    """Decorator that *injects* :class:`Depends` parameters.

    It supports

    * plain sync functions
    * coroutines
    * generator functions (as streaming endpoints)
    * async-generator functions
    * classes (fields initialised at ``__init__`` time)

    The decorator can be used with or without parentheses::

        @inject
        def handler(a: Annotated[int, Depends(int)]): ...

        @inject()
        async def coro(...): ...
    """

    # ---------------- inner helpers --------------------------------
    def _wrap_fn(fn: Callable[P, R]) -> Callable[P, R]:
        sig = inspect.signature(fn)
        is_coro = inspect.iscoroutinefunction(fn)
        is_gen = inspect.isgeneratorfunction(fn)
        is_async_gen = inspect.isasyncgenfunction(fn)

        # —— 4.1  Plain synchronous function ------------------------
        if not (is_coro or is_gen or is_async_gen):

            @wraps(fn)
            def wrapper(*args: P.args, **kw: P.kwargs):  # type: ignore[misc]
                bound = sig.bind_partial(*args, **kw)
                with ExitStack() as stack:
                    finals = _bind_all(sig, bound, stack=stack, astack=None)
                    try:
                        result = fn(**bound.arguments)  # type: ignore[arg-type]
                    except BaseException as exc:
                        _finalise_sync(finals, exc)
                        return None
                    _finalise_sync(finals, None)
                    return result

            return wrapper  # type: ignore[return-value]

        # —— 4.2  Coroutine -----------------------------------------
        if is_coro:

            @wraps(fn)
            async def wrapper(*args: P.args, **kw: P.kwargs):  # type: ignore[misc]
                bound = sig.bind_partial(*args, **kw)
                async with AsyncExitStack() as astack:
                    with ExitStack() as stack:
                        finals = _bind_all(sig, bound, stack=stack, astack=astack)
                        # await injected coroutine values
                        for k, v in list(bound.arguments.items()):
                            if isawaitable(v):
                                bound.arguments[k] = await v
                        try:
                            result = await fn(**bound.arguments)  # type: ignore[arg-type]
                        except BaseException as exc:
                            await _finalise_async(finals, exc)
                            return None
                        await _finalise_async(finals, None)
                        return result

            return wrapper  # type: ignore[return-value]

        # —— 4.3  *Sync* generator ----------------------------------
        if is_gen:

            @wraps(fn)
            def wrapper(*args: P.args, **kw: P.kwargs):  # type: ignore[misc]
                bound = sig.bind_partial(*args, **kw)
                with ExitStack() as stack:
                    finals = _bind_all(sig, bound, stack=stack, astack=None)
                    gen = fn(**bound.arguments)
                    try:
                        first = next(gen)
                    except StopIteration:
                        raise RuntimeError("Generator produced no value") from None

                    try:
                        yield first
                    except BaseException as exc:
                        try:
                            gen.throw(exc)
                        except StopIteration:  # swallowed
                            exc = None
                        except BaseException as inner:
                            exc = inner
                        _finalise_sync(finals, exc)
                    else:
                        gen.close()
                        _finalise_sync(finals, None)

            return wrapper  # type: ignore[return-value]

        # —— 4.4  Async-generator -----------------------------------
        @wraps(fn)
        async def wrapper(*args: P.args, **kw: P.kwargs):  # type: ignore[misc]
            bound = sig.bind_partial(*args, **kw)
            async with AsyncExitStack() as astack:
                with ExitStack() as stack:
                    finals = _bind_all(sig, bound, stack=stack, astack=astack)
                    for k, v in list(bound.arguments.items()):
                        if isawaitable(v):
                            bound.arguments[k] = await v

                    agen = fn(**bound.arguments)
                    try:
                        first = await agen.__anext__()
                    except StopAsyncIteration:
                        raise RuntimeError("Async-generator produced no value") from None

                    try:
                        yield first
                    except BaseException as exc:
                        try:
                            await agen.athrow(exc)
                        except StopAsyncIteration:
                            exc = None
                        except BaseException as inner:
                            exc = inner
                        await _finalise_async(finals, exc)
                    else:
                        await agen.aclose()
                        await _finalise_async(finals, None)

        return wrapper  # type: ignore[return-value]

    # ---------------- Class wrapper --------------------------------
    def _wrap_cls(cls: type) -> type:
        """Inject :class:`Depends` fields at construction."""
        orig_init = cls.__init__
        is_plain = orig_init is object.__init__

        @wraps(orig_init)
        def __init__(self, *args, **kwargs):  # type: ignore[no-self-use]
            injected: dict[str, Any] = {}
            for name, anno in getattr(cls, "__annotations__", {}).items():
                if get_origin(anno) is Annotated:
                    _, *extras = get_args(anno)
                    for e in extras:
                        if isinstance(e, Depends) and name not in kwargs:
                            injected[name] = _start_dep(e, allow_async=False).value
                            break

            if is_plain:  # dataclass-like, no custom __init__
                for k, v in injected.items():
                    setattr(self, k, v)
                orig_init(self)
            else:
                orig_init(self, *args, **{**injected, **kwargs})

        cls.__init__ = __init__  # type: ignore[assignment]
        return cls

    # ---------------- Dispatcher -----------------------------------
    def _apply(t):
        if inspect.isclass(t):
            return _wrap_cls(t)
        if callable(t):
            return _wrap_fn(t)  # type: ignore[arg-type]
        raise TypeError("@inject can only decorate a function or class")

    return _apply(target) if target is not None else _apply
