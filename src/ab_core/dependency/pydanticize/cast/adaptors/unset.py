"""Resolves ab_client 'Unset' type in pydanticize casting in DI."""

from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from .base import BaseTypePlugin


def _is_unset(t: Any) -> bool:
    # Be tolerant: some Unset types may be defined in different modules.
    # We identify by simple class/name equality.
    name = getattr(t, "__name__", None) or getattr(getattr(t, "__class__", None), "__name__", "")
    return name == "Unset"


class UnsetStripPlugin(BaseTypePlugin):
    @staticmethod
    def available() -> bool:
        # No external deps — always available.
        return True

    def matches(self, obj: Any) -> bool:
        origin = get_origin(obj)
        if origin is Union or origin is UnionType:
            return any(_is_unset(arg) for arg in get_args(obj))
        return False

    def upgrade(self, _type: Any) -> type[BaseModel]:
        """Remove any `Unset` members from a Union and pydanticize the result.

        Examples:
          Union[Unset, int, str]   -> Union[int, str]
          Unset | list[int] | None -> list[int] | None
          Union[Unset, T]          -> T
          Union[Unset]             -> Any   (degenerate case)

        """
        from ab_core.dependency.pydanticize.cast.helpers import PLUGINS, pydanticize_type
        args = tuple(a for a in get_args(_type) if not _is_unset(a))
        if not args:
            cleaned: Any = Any  # Degenerate: Union[Unset] -> Any
        elif len(args) == 1:
            cleaned = args[0]
        else:
            # Rebuild a typing.Union without Unset
            cleaned = Union[tuple(args)]  # type: ignore[arg-type]

        return pydanticize_type(cleaned)
