"""Plugin to convert attrs-decorated classes to Pydantic BaseModel classes."""

import inspect
from typing import TYPE_CHECKING, Any, get_type_hints, override

from pydantic import BaseModel, create_model, Field
from .base import BaseTypePlugin

HAS_ATTRS = True
try:
    from attrs import (
        NOTHING as _NOTHING,
    )
    from attrs import (
        fields as _fields,
    )
    from attrs import (
        has as _has,
    )
except ImportError:
    HAS_ATTRS = False
    _has = lambda _: False
    _fields = lambda _: []
    _NOTHING = object()

if TYPE_CHECKING:
    from attrs import (
        NOTHING,
        fields,
        has,
    )
else:
    has = _has
    fields = _fields
    NOTHING = _NOTHING


class AttrsPlugin(BaseTypePlugin):
    """A plugin that can convert attrs-decorated classes to Pydantic BaseModel classes."""

    @override
    @staticmethod
    def available() -> bool:
        return HAS_ATTRS

    @override
    def matches(self, obj: Any) -> bool:
        return inspect.isclass(obj) and has(obj)

    @override
    def upgrade(
        self,
        _type: type,
    ) -> type[BaseModel]:
        """Convert an attrs-decorated class to a Pydantic BaseModel."""
        from ab_core.dependency.pydanticize import is_supported_by_pydantic, pydanticize_type

        # Name used for the generated model
        name = f"{_type.__name__}"

        # Resolve annotations with extras and forward refs
        hints = get_type_hints(_type, include_extras=True)

        pyd_fields: dict[str, tuple[type[Any], Any]] = {}

        for f in fields(_type):
            attr_name = f.name
            ann = hints.get(attr_name, Any)

            # If Pydantic already supports this type directly, keep it.
            # Otherwise, recursively "pydanticize" the type (this will route to
            # the correct plugin, including this one for nested attrs classes).
            try:
                if not is_supported_by_pydantic(ann):
                    ann = pydanticize_type(ann)
            except Exception:
                # Don't mask adapter/plugin errors: surface them so callers see
                # that this plugin doesn't support the provided type.
                raise

            # Determine default / default_factory from attrs field
            default_value = f.default
            default_factory = getattr(f.default, "factory", None)

            if default_factory is not None:
                # attrs uses a Factory wrapper for factories; pydantic expects Field(default_factory=...)
                pyd_fields[attr_name] = (ann, Field(default_factory=default_factory))
            elif default_value is not NOTHING:
                pyd_fields[attr_name] = (ann, default_value)
            else:
                # Required field
                pyd_fields[attr_name] = (ann, ...)

        Model = create_model(
            name,
            __base__=BaseModel,
            **pyd_fields,
        )
        return Model
