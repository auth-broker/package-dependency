"""Plugin to convert attrs-decorated classes to Pydantic BaseModel classes."""

import inspect
from typing import TYPE_CHECKING, Any, get_type_hints, override

from pydantic import BaseModel, Field, create_model

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

        name = _type.__name__
        hints = get_type_hints(_type, include_extras=True)
        pyd_fields: dict[str, tuple[type[Any], Any]] = {}

        for f in fields(_type):
            attr_name = f.name
            ann = hints.get(attr_name, Any)
            if not is_supported_by_pydantic(ann):
                ann = pydanticize_type(ann)

            default_value = f.default
            default_factory = getattr(f.default, "factory", None)

            if default_factory is not None:
                pyd_fields[attr_name] = (ann, Field(default_factory=default_factory))
            elif default_value is not NOTHING:
                pyd_fields[attr_name] = (ann, default_value)
            else:
                pyd_fields[attr_name] = (ann, ...)

        # ---- build a dynamic mixin that carries methods/props/constants ----
        mixin_ns: dict[str, Any] = {}

        def _is_descriptor(obj: object) -> bool:
            return isinstance(obj, (property, classmethod, staticmethod))

        def _should_include_member(name: str, obj: object) -> bool:
            if name.startswith("__") and name.endswith("__"):
                return False  # keep dunders out by default
            if name in pyd_fields:  # fields are set by create_model
                return False
            # include instance methods, descriptors, and non-callable class constants
            return inspect.isfunction(obj) or _is_descriptor(obj) or (not callable(obj))

        for m_name, obj in inspect.getmembers(_type):
            if _should_include_member(m_name, obj):
                mixin_ns[m_name] = obj

        # preserve docstring for niceness
        if getattr(_type, "__doc__", None):
            mixin_ns.setdefault("__doc__", _type.__doc__)

        MethodsMixin = type(f"{name}MethodsMixin", (BaseModel,), mixin_ns)

        # ---- now create the actual model, using the mixin as the base ----
        Model = create_model(
            name,
            __base__=MethodsMixin,
            **pyd_fields,
        )
        Model.__module__ = getattr(_type, "__module__", Model.__module__)
        return Model
