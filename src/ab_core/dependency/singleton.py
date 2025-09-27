from typing import Any, TypeVar

from pydantic import BaseModel

from .types import LoadTarget

T = TypeVar("T", bound=BaseModel)


class SingletonRegistryMeta(type):
    _instances: dict[tuple[Any, Any], BaseModel] = {}

    def __call__(cls, loader: LoadTarget[T], key: Any) -> T:
        if key not in cls._instances:
            cls._instances[key] = loader()
        return cls._instances[key]  # type: ignore


class SingletonRegistry(metaclass=SingletonRegistryMeta): ...
