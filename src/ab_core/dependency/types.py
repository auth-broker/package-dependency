from collections.abc import Callable
from typing import (
    Annotated,
    Any,
    TypeVar,
)

from .loaders.base import LoaderBase

T = TypeVar("T")

LoadTarget = Callable[..., T] | type[T] | LoaderBase[T] | Annotated[T | Any, Any]
