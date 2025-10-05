"""Plugin to convert attrs-decorated classes to Pydantic BaseModel classes."""

import inspect
import logging
from typing import TYPE_CHECKING, Any, get_type_hints, override

from pydantic import BaseModel, Field, create_model, PrivateAttr, ConfigDict

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

logger = logging.getLogger(__name__)


def _as_private_attr_default(default_val: Any) -> Any:
    # Pydantic v2 PrivateAttr(default=...) expects the raw default
    return default_val if default_val is not NOTHING else None


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
    def upgrade(self, _type: type) -> type[BaseModel]:  # override
        from ab_core.dependency.pydanticize import is_supported_by_pydantic, pydanticize_type

        name = _type.__name__
        hints = get_type_hints(_type, include_extras=True)

        pyd_fields: dict[str, tuple[type[Any], Any]] = {}
        private_attrs: dict[str, PrivateAttr] = {}
        underscore_proxies: dict[str, str] = {}       # underscored field name -> public field name
        private_name_proxies: dict[str, str] = {}     # public name -> sunder PrivateAttr name

        need_arbitrary_types = False

        # — NEW: track attrs field names and the sunder names we’ll create for private attrs
        attrs_field_names = set()
        private_attr_sunder_names = set()

        for f in fields(_type):
            attr_name = f.name
            attrs_field_names.add(attr_name)  # <-- NEW
            ann = hints.get(attr_name, Any)

            # Treat init=False attrs as private attributes (not model fields)
            if getattr(f, "init", True) is False:
                private_name = attr_name if attr_name.startswith("_") else f"_{attr_name}"
                private_attrs[private_name] = PrivateAttr(default=_as_private_attr_default(f.default))
                private_attr_sunder_names.add(private_name)  # <-- NEW
                if private_name != attr_name:
                    private_name_proxies[attr_name] = private_name
                continue

            # Compute public Pydantic field name (alias preferred; else strip leading "_")
            alias = getattr(f, "alias", None)
            if alias:
                public_name = alias
                if attr_name.startswith("_"):
                    underscore_proxies[attr_name] = public_name
            elif attr_name.startswith("_"):
                public_name = attr_name.lstrip("_")
                underscore_proxies[attr_name] = public_name
            else:
                public_name = attr_name

            try:
                if not is_supported_by_pydantic(ann):
                    ann = pydanticize_type(ann)  # may raise
            except Exception as e:
                logger.warning(
                    f"Sub annotation `{attr_name}: {repr(ann)}` from your attrs model `{_type}`"
                    f" could not be casted as pydantic suportted type due to: {e}. Therefore,"
                    f" we are enabling `arbitrary_types_allowed` on the casted pydantic model."
                )
                need_arbitrary_types = True

            default_value = f.default
            default_factory = getattr(f.default, "factory", None)

            if default_factory is not None:
                pyd_fields[public_name] = (ann, Field(default_factory=default_factory))
            elif default_value is not NOTHING:
                pyd_fields[public_name] = (ann, default_value)
            else:
                pyd_fields[public_name] = (ann, ...)

        # ---- dynamic mixin to carry methods/props/constants ----
        mixin_ns: dict[str, Any] = {}

        def _is_descriptor(obj: object) -> bool:
            return isinstance(obj, (property, classmethod, staticmethod))

        def _should_include_member(m_name: str, obj: object) -> bool:
            # Exclude dunders
            if m_name.startswith("__") and m_name.endswith("__"):
                return False
            # Exclude any name that corresponds to a Pydantic field
            if m_name in pyd_fields:
                return False
            # NEW: Exclude ALL attrs field names (prevents slot members from leaking in)
            if m_name in attrs_field_names:
                return False
            # NEW: Also exclude the sunder names we just created for PrivateAttr
            if m_name in private_attr_sunder_names:
                return False
            # Allow instance methods, descriptors, and non-callable constants
            return inspect.isfunction(obj) or _is_descriptor(obj) or (not callable(obj))

        for m_name, obj in inspect.getmembers(_type):
            if _should_include_member(m_name, obj):
                mixin_ns[m_name] = obj

        if getattr(_type, "__doc__", None):
            mixin_ns.setdefault("__doc__", _type.__doc__)

        mixin_ns.update(private_attrs)

        base_config = ConfigDict(arbitrary_types_allowed=need_arbitrary_types)
        MethodsMixin = type(f"{name}MethodsMixin", (BaseModel,), {"model_config": base_config, **mixin_ns})

        Model = create_model(
            name,
            __base__=MethodsMixin,
            **pyd_fields,
        )
        Model.__module__ = getattr(_type, "__module__", Model.__module__)

        # Proxies: underscored attrs -> public fields
        for underscored, public in underscore_proxies.items():
            def _getter(self, _pub=public):
                return getattr(self, _pub)
            def _setter(self, value, _pub=public):
                setattr(self, _pub, value)
            setattr(Model, underscored, property(_getter, _setter))

        # Proxies: public name -> sunder PrivateAttr (for init=False like additional_properties)
        for public, private in private_name_proxies.items():
            if public in pyd_fields:
                continue
            def _p_getter(self, _priv=private):
                return getattr(self, _priv)
            def _p_setter(self, value, _priv=private):
                setattr(self, _priv, value)
            setattr(Model, public, property(_p_getter, _p_setter))

        return Model
