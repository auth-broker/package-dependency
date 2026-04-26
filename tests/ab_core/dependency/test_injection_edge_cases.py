from typing import Annotated

import pytest
from pydantic import BaseModel

from ab_core.dependency import Depends, Load, inject
from ab_core.dependency.singleton import SingletonRegistryMeta


@pytest.fixture(autouse=True)
def clear_singleton_registry_between_tests():
    SingletonRegistryMeta._instances.clear()
    yield
    SingletonRegistryMeta._instances.clear()


@pytest.mark.asyncio
async def test_async_function_can_depend_on_sync_generator_loader():
    tracker = {"closed": 0}

    def sync_gen():
        try:
            yield "sync-gen"
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(value: Annotated[str, Depends(sync_gen)]):
        return value

    assert await fn() == "sync-gen"
    assert tracker["closed"] == 1


@pytest.mark.asyncio
async def test_async_function_sync_generator_dependency_receives_exception():
    tracker = {"closed": 0, "caught": None}

    def sync_gen():
        try:
            yield "sync-gen"
        except Exception as exc:
            tracker["caught"] = exc
            raise
        finally:
            tracker["closed"] += 1

    @inject
    async def fn(value: Annotated[str, Depends(sync_gen)]):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await fn()

    assert tracker["closed"] == 1
    assert isinstance(tracker["caught"], RuntimeError)


class PersistentConfig(BaseModel):
    value: str = "default"


def test_persistent_dependency_is_cached_within_test():
    first = Load(PersistentConfig, persist=True)
    first.value = "changed"

    second = Load(PersistentConfig, persist=True)

    assert first is second
    assert second.value == "changed"


def test_singleton_registry_isolation_starts_each_test_empty():
    assert SingletonRegistryMeta._instances == {}

    loaded = Load(PersistentConfig, persist=True)

    assert loaded == PersistentConfig(value="default")
    assert len(SingletonRegistryMeta._instances) == 1
