from typing import (
    Annotated,
    Any,
    Callable,
    Type,
    TypeVar,
    Union,
)

from .loaders.base import LoaderBase

T = TypeVar("T")

LoadTarget = Callable[..., T] | Type[T] | LoaderBase[T] | Annotated[Union[T, Any], Any]
