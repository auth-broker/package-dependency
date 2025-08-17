from pydantic import BaseModel

from ab_core.dependency.loaders import ObjectLoaderEnvironment
from ab_core.dependency.singleton import SingletonRegistry


class DummyModel(BaseModel):
    foo: str = "bar"


def test_singleton_registry_returns_same_instance():
    instance_1 = SingletonRegistry(ObjectLoaderEnvironment[DummyModel](), key=DummyModel)
    instance_2 = SingletonRegistry(ObjectLoaderEnvironment[DummyModel](), key=DummyModel)

    # Identity check
    assert instance_1 is instance_2

    # Functional check
    assert isinstance(instance_1, DummyModel)
