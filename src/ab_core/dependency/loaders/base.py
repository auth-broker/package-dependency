from abc import ABC, abstractmethod
from copy import deepcopy
from functools import cached_property
from typing import (
    Any,
    TypeVar,
)

from generic_preserver.wrapper import generic_preserver
from pydantic import BaseModel, Discriminator, TypeAdapter, model_validator
from pydantic_core.core_schema import CoreSchema

from ab_core.dependency.pydanticize import cached_type_adapter, pydanticize_data, pydanticize_type
from ab_core.dependency.utils import extract_target_types, type_name_intersection

T = TypeVar("T")


@generic_preserver
class LoaderBase[T](BaseModel, ABC):
    """Base class for all loaders."""

    default_value: T | None = None

    def __call__(
        self,
    ) -> T:
        """Load and return the data of the specified type."""
        return self.load()

    @abstractmethod
    def load_raw(
        self,
    ) -> Any:
        """Load the raw data before any processing."""
        ...

    def load(
        self,
    ) -> T:
        """Load and return the data of the specified type, applying type plugins."""
        try:
            data = self.load_raw()
        except Exception as e:
            raise RuntimeError(f"Error loading `{repr(self.type)}`: {e}") from e
        if not data and self.default_value:
            return self.default_value
        data_restructured = pydanticize_data(deepcopy(data), self.core_schema)
        return self.type_adaptor.validate_python(data_restructured)

    @cached_property
    def native_type(self) -> type[T]:
        """The native type T, without any type plugins applied."""
        return self[T]

    @cached_property
    def type(self) -> type[T]:
        """The type T, with any type plugins applied."""
        return pydanticize_type(self.native_type)

    @cached_property
    def type_adaptor(self) -> TypeAdapter:
        """Generates a TypeAdapter for the type, applying any type plugins."""
        return cached_type_adapter(self.type)

    @cached_property
    def core_schema(self) -> CoreSchema:
        """Generates the core schema for the type, applying any type plugins."""
        return self.type_adaptor.core_schema

    @classmethod
    def supports(cls, obj: Any) -> bool:
        """Check if the loader supports the given type."""
        try:
            pydanticize_type(obj)
            return True
        except TypeError:
            return False


class ObjectLoaderBase(LoaderBase[T], ABC):
    """Base class for loaders that handle Pydantic BaseModel objects."""

    default_discriminator_value: Any = None
    discriminator_key: str | None = None

    @model_validator(mode="after")
    def validate_type(self):
        """Ensure that the type is a BaseModel or a Union of BaseModels."""
        if len(self.types) == 0:
            raise Exception(f"Unable to find any BaseModel types in {repr(self.type)}")
        if self.discriminator:
            self.discriminator_key = self.discriminator.discriminator
        return self

    @property
    def alias_name(self) -> str:
        """Generates an alias name for the loader based on the intersection of type names."""
        assumed_name = type_name_intersection(self.types)
        if not assumed_name:
            raise ValueError(
                f"Unable to create an alias for types `{repr(self.types)}`."
                " Ensure there is a naming overlap between each of the types."
            )
        return assumed_name

    @cached_property
    def types(self) -> list[type[BaseModel]]:
        """Extracts all BaseModel types from the provided type."""
        return list(extract_target_types(self.type, BaseModel))

    @cached_property
    def discriminator(self) -> Discriminator | None:
        """Extracts the Discriminator if one exists in the provided type."""
        try:
            return next(extract_target_types(self.type, Discriminator))
        except StopIteration:
            return None

    @cached_property
    def discriminator_choices(self) -> list[str] | None:
        """Extracts the discriminator choices if a discriminator is defined."""
        if not self.discriminator:
            return None
        return [_type.model_fields[self.discriminator_key].default for _type in self.types]

    def discriminate_type(
        self,
    ) -> type[T]:
        """Determine the specific type to use based on the discriminator value."""
        if self.discriminator is None:
            return self.type

        discriminator_value = self.load_raw()[self.discriminator_key]
        return self.type_adaptor.core_schema["choices"][discriminator_value]["schema"]["schema"]["cls"]
