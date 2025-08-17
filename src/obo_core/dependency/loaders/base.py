from abc import ABC, abstractmethod
from copy import deepcopy
from functools import cached_property
from typing import (
    Any,
    Generic,
    Optional,
    Type,
    TypeVar,
)

from generic_preserver.wrapper import generic_preserver
from pydantic import BaseModel, Discriminator, TypeAdapter, model_validator
from pydantic_core.core_schema import CoreSchema

from obo_core.dependency.utils import extract_target_types, type_name_intersection

from ..pydanticize import pydanticize

T = TypeVar("T")


@generic_preserver
class LoaderBase(BaseModel, Generic[T], ABC):
    default_value: Optional[T] = None

    def __call__(
        self,
    ) -> T:
        """Factory entrypoint so we can directly call the loader."""
        return self.load()

    @abstractmethod
    def load_raw(
        self,
    ) -> Any: ...

    def load(
        self,
    ) -> T:
        try:
            data = self.load_raw()
        except Exception as e:
            raise RuntimeError(f"Error loading `{repr(self.type)}`: {e}") from e
        if not data and self.default_value:
            return self.default_value
        data_restructured = pydanticize(deepcopy(data), self.core_schema)
        return self.type_adaptor.validate_python(data_restructured)

    @property
    def type(self) -> Type[T]:
        return self[T]

    @property
    def type_adaptor(self) -> TypeAdapter:
        return TypeAdapter(self.type)

    @property
    def core_schema(self) -> CoreSchema:
        return self.type_adaptor.core_schema

    @classmethod
    def supports(cls, obj: Any) -> bool:
        try:
            TypeAdapter(obj)
            return True
        except Exception:
            return False


class ObjectLoaderBase(LoaderBase[T], ABC):
    default_discriminator_value: Optional[Any] = None
    discriminator_key: Optional[str] = None

    @model_validator(mode="after")
    def validate_type(self):
        if len(self.types) == 0:
            raise Exception(f"Unable to find any BaseModel types in {repr(self.type)}")
        if self.discriminator:
            self.discriminator_key = self.discriminator.discriminator
        return self

    @property
    def alias_name(self) -> str:
        assumed_name = type_name_intersection(self.types)
        if not assumed_name:
            raise ValueError(
                f"Unable to create an alias for types `{repr(self.types)}`."
                " Ensure there is a naming overlap between each of the types."
            )
        return assumed_name

    @cached_property
    def types(self) -> list[type[BaseModel]]:
        return list(extract_target_types(self.type, BaseModel))

    @cached_property
    def discriminator(self) -> Optional[Discriminator]:
        try:
            return next(extract_target_types(self.type, Discriminator))
        except StopIteration:
            return None

    @cached_property
    def discriminator_choices(self) -> Optional[list[str]]:
        if not self.discriminator:
            return None
        return [_type.model_fields[self.discriminator_key].default for _type in self.types]

    def discriminate_type(
        self,
    ) -> Type[T]:
        if self.discriminator is None:
            return self.type

        discriminator_value = self.load_raw()[self.discriminator_key]
        return self.type_adaptor.core_schema["choices"][discriminator_value]["schema"]["schema"][
            "cls"
        ]
