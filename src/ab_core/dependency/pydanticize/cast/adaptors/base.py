"""Base class for type plugins."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class BaseTypePlugin(BaseModel, ABC):
    """A plugin that can convert a specific type of object to a Pydantic BaseModel."""

    @staticmethod
    @abstractmethod
    def available() -> bool:
        """Return True if the plugin can be used (e.g., required packages are installed)."""
        ...

    @abstractmethod
    def matches(self, obj: Any) -> bool:
        """Return True if the plugin can handle the given object."""
        ...

    @abstractmethod
    def upgrade(self, _type: Any) -> type[BaseModel]:
        """Convert the given object to a Pydantic BaseModel."""
        ...
