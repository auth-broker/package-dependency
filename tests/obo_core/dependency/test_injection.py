"""
Comprehensive test-suite for obo_core.dependency.Depends.

New in this revision
--------------------
• Generator-loader tests no longer wrap the generator in a lambda.
  Instead, the actual **generator function** is passed to `Depends`, so
  the DI system can correctly detect and manage its lifecycle.
"""

import asyncio
import inspect
from typing import Annotated, Any

import pytest
from pydantic import BaseModel

from obo_core.dependency import Depends, inject, sentinel

# ------------------------------------------------------------------ #
# Dummy dependencies                                                 #
# ------------------------------------------------------------------ #


class Foo(BaseModel):
    value: str = "foo"


class Bar(BaseModel):
    value: str = "bar"


# ------------------------------------------------------------------ #
# 1) Sync function injection tests (existing)                        #
# ------------------------------------------------------------------ #


def test_function_injection_works():
    @inject
    def my_function(
        param: Any,
        foo: Annotated[Foo, Depends(Foo)],
        bar_1: Annotated[Bar, Depends(Bar, persist=True)],
        bar_2: Annotated[Bar, Depends(Bar, persist=True)],
        bar_3: Annotated[Bar, Depends(Bar, persist=False)],
    ):
        assert param is None

        assert isinstance(foo, Foo) and foo.value == "foo"

        assert isinstance(bar_1, Bar) and bar_1.value == "bar"
        assert isinstance(bar_2, Bar)
        assert isinstance(bar_3, Bar)

        # persistence / transient checks
        assert bar_1 is bar_2
        assert bar_1 is not bar_3
        assert bar_2 is not bar_3
        assert bar_2 == bar_3

    my_function(None)


def test_function_injection_works_sentinel():
    @inject
    def my_function(
        param: Any,
        *,
        foo: Annotated[Foo, Depends(Foo)] = sentinel(),
        bar_1: Annotated[Bar, Depends(Bar, persist=True)] = sentinel(),
        bar_2: Annotated[Bar, Depends(Bar, persist=True)] = sentinel(),
        bar_3: Annotated[Bar, Depends(Bar, persist=False)] = sentinel(),
    ):
        assert param is None

        assert isinstance(foo, Foo) and foo.value == "foo"

        assert isinstance(bar_1, Bar) and bar_1.value == "bar"
        assert isinstance(bar_2, Bar)
        assert isinstance(bar_3, Bar)

        # persistence / transient checks
        assert bar_1 is bar_2
        assert bar_1 is not bar_3
        assert bar_2 is not bar_3
        assert bar_2 == bar_3

    my_function(None)


# ------------------------------------------------------------------ #
# 2) Async function injection tests (new)                            #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_async_function_injection_works():
    @inject
    async def my_async_function(
        param: Any,
        foo: Annotated[Foo, Depends(Foo)],
        bar_1: Annotated[Bar, Depends(Bar, persist=True)],
        bar_2: Annotated[Bar, Depends(Bar, persist=True)],
        bar_3: Annotated[Bar, Depends(Bar, persist=False)],
    ) -> str:
        assert param is None
        assert isinstance(foo, Foo) and foo.value == "foo"

        assert isinstance(bar_1, Bar) and bar_1.value == "bar"
        assert isinstance(bar_2, Bar)
        assert isinstance(bar_3, Bar)

        assert bar_1 is bar_2
        assert bar_1 is not bar_3
        assert bar_2 is not bar_3
        assert bar_2 == bar_3

        return "OK"

    result = await my_async_function(None)
    assert result == "OK"


# ------------------------------------------------------------------ #
# 3) Class injection test (existing)                                 #
# ------------------------------------------------------------------ #


def test_class_injection_works():
    @inject
    class MySettings:
        foo1: Annotated[Foo, Depends(Foo)]
        foo2: Annotated[Foo, Depends(Foo)]
        bar_1: Annotated[Bar, Depends(Bar, persist=True)]
        bar_2: Annotated[Bar, Depends(Bar, persist=True)]
        bar_3: Annotated[Bar, Depends(Bar, persist=False)]
        some_int: int = 123

    s1 = MySettings()
    assert isinstance(s1.foo1, Foo) and s1.foo1.value == "foo"
    assert isinstance(s1.foo2, Foo)
    assert s1.foo1 is not s1.foo2

    assert s1.bar_2 is s1.bar_1
    assert s1.bar_3 is not s1.bar_1
    assert s1.some_int == 123

    s2 = MySettings()
    assert s2.bar_1 is s1.bar_1  # persistent
    assert s2.foo1 is not s1.foo1  # transient


# ------------------------------------------------------------------ #
# 4) Pydantic model DI-call counting (existing)                      #
# ------------------------------------------------------------------ #


def test_pydantic_model_injection_calls_only_depends():
    calls = {"foo": 0, "bar": 0}

    class CountingDepends(Depends):
        def __init__(self, type_or_loader, *, persist: bool = False, key: str):
            super().__init__(type_or_loader, persist=persist)
            self.key = key

        def __call__(self):
            calls[self.key] += 1
            return super().__call__()

    @inject
    class MyConfig(BaseModel):
        foo: Annotated[Foo, CountingDepends(Foo, key="foo")]
        bar: Annotated[Bar, CountingDepends(Bar, persist=True, key="bar")]
        count: int = 42

    MyConfig()
    assert calls == {"foo": 1, "bar": 1}

    MyConfig(bar=Bar())
    assert calls == {"foo": 2, "bar": 1}

    raw = {"foo": {"value": "from_data"}, "bar": {"value": "from_data"}, "count": 999}
    MyConfig.model_validate(raw)
    assert calls == {"foo": 2, "bar": 1}


# ------------------------------------------------------------------ #
# 5) Gen-function DI (existing)                                      #
# ------------------------------------------------------------------ #


def test_gen_function_injection_works():
    @inject
    def gen(bar: Annotated[Bar, Depends(Bar, persist=True)]):
        yield bar

    assert inspect.isgeneratorfunction(gen)

    b1 = next(gen())
    b2 = next(gen())
    assert b1 is b2  # persistent


@pytest.mark.asyncio
async def test_async_gen_function_injection_works():
    @inject
    async def agen(bar: Annotated[Bar, Depends(Bar, persist=True)]):
        yield bar

    assert inspect.isasyncgenfunction(agen)

    b1 = await agen().__anext__()  # type: ignore[attr-defined]
    b2 = await agen().__anext__()  # type: ignore[attr-defined]
    assert b1 is b2


# ------------------------------------------------------------------ #
# 6) Depends with callable loaders (function & async fn)             #
# ------------------------------------------------------------------ #


def test_depends_with_sync_callable_loader():
    def make_value() -> str:
        return "sync-callable"

    @inject
    def func(value: Annotated[str, Depends(make_value)]):
        return value

    assert func() == "sync-callable"


@pytest.mark.asyncio
async def test_depends_with_async_callable_loader():
    async def make_value() -> str:
        await asyncio.sleep(0)
        return "async-callable"

    @inject
    async def func(value: Annotated[str, Depends(make_value)]):
        return value

    assert await func() == "async-callable"


# ------------------------------------------------------------------ #
# 7) Depends with **sync generator** loader                          #
# ------------------------------------------------------------------ #


def test_depends_with_sync_generator_loader_success():
    tracker = {"closed": 0}

    def sync_gen():
        try:
            yield "sync-gen"
        finally:
            tracker["closed"] += 1

    @inject
    def fn(value: Annotated[str, Depends(sync_gen)]):
        assert tracker["closed"] == 0
        return value

    assert fn() == "sync-gen"
    assert tracker["closed"] == 1


def test_depends_with_sync_generator_loader_exception():
    tracker = {"closed": 0}

    def sync_gen():
        try:
            yield "sync-gen"
        finally:
            tracker["closed"] += 1

    @inject
    def fn(value: Annotated[str, Depends(sync_gen)]):
        assert tracker["closed"] == 0
        raise RuntimeError("explode")

    with pytest.raises(RuntimeError):
        fn()

    assert tracker["closed"] == 1


# ------------------------------------------------------------------ #
# 8) Depends with **async generator** loader                         #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_depends_with_async_generator_loader_success():
    tracker = {"closed": 0}

    async def async_gen():
        try:
            yield "async-gen"
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(value: Annotated[str, Depends(async_gen)]):
        assert tracker["closed"] == 0
        return value

    assert await fn() == "async-gen"
    assert tracker["closed"] == 1


@pytest.mark.asyncio
async def test_depends_with_async_generator_loader_exception():
    tracker = {"closed": 0}

    async def async_gen():
        try:
            yield "async-gen"
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(value: Annotated[str, Depends(async_gen)]):
        assert tracker["closed"] == 0
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await fn()

    assert tracker["closed"] == 1


# ------------------------------------------------------------------ #
# 9) NEW – Generator loaders with *except* handling                  #
# ------------------------------------------------------------------ #


def test_sync_generator_loader_handles_exception_block():
    tracker = {"closed": 0, "caught": None}

    def sync_gen():
        try:
            yield "sync-gen"
        except Exception as e:  # should receive the thrown error
            tracker["caught"] = e
            raise
        finally:
            tracker["closed"] += 1

    @inject
    def fn(val: Annotated[str, Depends(sync_gen)]):
        raise ValueError("kaboom")

    with pytest.raises(ValueError):
        fn()

    assert tracker["closed"] == 1
    assert isinstance(tracker["caught"], ValueError)


@pytest.mark.asyncio
async def test_async_generator_loader_handles_exception_block():
    tracker = {"closed": 0, "caught": None}

    async def async_gen():
        try:
            yield "async-gen"
        except Exception as e:
            tracker["caught"] = e
            raise
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(val: Annotated[str, Depends(async_gen)]):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await fn()

    assert tracker["closed"] == 1
    assert isinstance(tracker["caught"], RuntimeError)


# ------------------------------------------------------------------ #
# 10) NEW – Generator loaders with *except* handling, but no re-raise                  #
# ------------------------------------------------------------------ #


def test_sync_generator_loader_handles_exception_block_no_reraise():
    tracker = {"closed": 0, "caught": None}

    def sync_gen():
        try:
            yield "sync-gen"
        except Exception as e:  # should receive the thrown error
            tracker["caught"] = e
        finally:
            tracker["closed"] += 1

    @inject
    def fn(val: Annotated[str, Depends(sync_gen)]):
        raise ValueError("kaboom")

    result = fn()

    assert result is None
    assert tracker["closed"] == 1
    assert isinstance(tracker["caught"], ValueError)


@pytest.mark.asyncio
async def test_async_generator_loader_handles_exception_block_no_reraise():
    tracker = {"closed": 0, "caught": None}

    async def async_gen():
        try:
            yield "async-gen"
        except Exception as e:
            tracker["caught"] = e
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(val: Annotated[str, Depends(async_gen)]):
        raise RuntimeError("boom")

    result = await fn()

    assert result is None
    assert tracker["closed"] == 1
    assert isinstance(tracker["caught"], RuntimeError)


# ------------------------------------------------------------------ #
# 11) NEW – async-generator loader *with its own dependency*         #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_async_gen_loader_with_dep_success():
    tracker = {"closed": 0, "caught": None}

    @inject
    async def async_gen(foo: Annotated[Foo, Depends(Foo)]):
        assert isinstance(foo, Foo) and foo.value == "foo"
        try:
            yield f"{foo.value}-gen"
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(val: Annotated[str, Depends(async_gen)]):
        assert tracker["closed"] == 0
        return val

    assert await fn() == "foo-gen"
    assert tracker == {"closed": 1, "caught": None}


@pytest.mark.asyncio
async def test_async_gen_loader_with_dep_exception():
    tracker = {"closed": 0, "caught": None}

    @inject
    async def async_gen(foo: Annotated[Foo, Depends(Foo)]):
        try:
            yield "async-gen"
        except Exception as exc:
            tracker["caught"] = exc  # ← should receive RuntimeError
            raise
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(val: Annotated[str, Depends(async_gen)]):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await fn()

    assert tracker["closed"] == 1 and isinstance(tracker["caught"], RuntimeError)


@pytest.mark.asyncio
async def test_async_gen_loader_with_dep_exception_no_reraise():
    tracker = {"closed": 0, "caught": None}

    @inject
    async def async_gen(foo: Annotated[Foo, Depends(Foo)]):
        try:
            yield "async-gen"
        except Exception as exc:
            tracker["caught"] = exc  # ← should receive RuntimeError
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(val: Annotated[str, Depends(async_gen)]):
        raise RuntimeError("boom")

    result = await fn()

    assert result is None
    assert tracker["closed"] == 1 and isinstance(tracker["caught"], RuntimeError)


# ------------------------------------------------------------------ #
# 12) NEW – sync-generator loader *with its own dependency*          #
# ------------------------------------------------------------------ #


def test_sync_gen_loader_with_dep_success():
    tracker = {"closed": 0, "caught": None}

    @inject
    def sync_gen(foo: Annotated[Foo, Depends(Foo)]):  # ← inner dep
        assert isinstance(foo, Foo) and foo.value == "foo"
        try:
            yield f"{foo.value}-gen"
        finally:
            tracker["closed"] += 1

    @inject
    def fn(val: Annotated[str, Depends(sync_gen)]):
        assert tracker["closed"] == 0
        return val

    assert fn() == "foo-gen"
    assert tracker == {"closed": 1, "caught": None}


def test_sync_gen_loader_with_dep_exception():
    tracker = {"closed": 0, "caught": None}

    @inject
    def sync_gen(foo: Annotated[Foo, Depends(Foo)]):
        try:
            yield "sync-gen"
        except Exception as exc:
            tracker["caught"] = exc  # should get ValueError
            raise
        finally:
            tracker["closed"] += 1

    @inject
    def fn(val: Annotated[str, Depends(sync_gen)]):
        raise ValueError("kaboom")

    with pytest.raises(ValueError):
        fn()

    assert tracker["closed"] == 1 and isinstance(tracker["caught"], ValueError)


def test_sync_gen_loader_with_dep_exception_no_reraise():
    tracker = {"closed": 0, "caught": None}

    @inject
    def sync_gen(foo: Annotated[Foo, Depends(Foo)]):
        try:
            yield "sync-gen"
        except Exception as exc:
            tracker["caught"] = exc  # should get ValueError
        finally:
            tracker["closed"] += 1

    @inject
    def fn(val: Annotated[str, Depends(sync_gen)]):
        raise ValueError("kaboom")

    result = fn()

    assert result is None
    assert tracker["closed"] == 1 and isinstance(tracker["caught"], ValueError)
