"""Plugin to convert attrs-decorated classes to Pydantic BaseModel classes."""

import inspect
import logging
import sys
from functools import cached_property as _cached_property  # py3.8+: available
from typing import TYPE_CHECKING, Any, get_type_hints, override

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, create_model

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

        # Resolve hints with module globals to handle ForwardRef / Annotated / Self, etc.
        mod = sys.modules.get(getattr(_type, "__module__", ""), None)
        globalns = getattr(mod, "__dict__", None)
        try:
            hints = get_type_hints(_type, include_extras=True, globalns=globalns)
        except Exception as e:  # extremely defensive: fall back if resolution fails
            logger.debug("get_type_hints failed for %s due to %r; falling back to empty hints", _type, e)
            hints = {}

        pyd_fields: dict[str, tuple[type[Any], Any]] = {}
        private_attrs: dict[str, PrivateAttr] = {}
        underscore_proxies: dict[str, str] = {}  # underscored field name -> public field name
        private_name_proxies: dict[str, str] = {}  # public name -> sunder PrivateAttr name

        need_arbitrary_types = False

        # Track attr field names and the sunder names we create for private attrs
        attrs_field_names: set[str] = set()
        private_attr_sunder_names: set[str] = set()

        # Map of public field names to original attrs names to guard alias collisions
        public_name_owner: dict[str, str] = {}

        for f in fields(_type):
            attr_name = f.name
            attrs_field_names.add(attr_name)
            ann = hints.get(attr_name, Any)

            # Treat init=False attrs as private attributes (not model fields)
            if getattr(f, "init", True) is False:
                private_name = attr_name if attr_name.startswith("_") else f"_{attr_name}"
                private_attrs[private_name] = PrivateAttr(default=_as_private_attr_default(f.default))
                private_attr_sunder_names.add(private_name)
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

            # Guard: duplicate public name collisions (aliases or underscore-stripping)
            prev = public_name_owner.get(public_name)
            if prev is not None and prev != attr_name:
                raise ValueError(
                    f"attrs→pydantic: public field name collision for '{public_name}': "
                    f"from '{prev}' and '{attr_name}' in {_type!r}"
                )
            public_name_owner[public_name] = attr_name

            try:
                if not is_supported_by_pydantic(ann):
                    ann = pydanticize_type(ann)  # may raise
            except Exception as e:
                logger.warning(
                    f"Sub annotation `{attr_name}: {repr(ann)}` from your attrs model `{_type}` "
                    f"could not be cast as a Pydantic-supported type due to: {e}. Therefore, "
                    f"we are enabling `arbitrary_types_allowed` on the casted Pydantic model."
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
            # property / classmethod / staticmethod / cached_property
            return (
                isinstance(obj, (property, classmethod, staticmethod)) or isinstance(obj, _cached_property)  # type: ignore[arg-type]
            )

        # Explicitly allow the 4 context-manager dunders (fixes async CM support)
        _ALLOWED_DUNDERS = {"__enter__", "__exit__", "__aenter__", "__aexit__"}

        def _should_include_member(m_name: str, obj: object) -> bool:
            # Allow CM dunders explicitly
            if m_name in _ALLOWED_DUNDERS:
                return True
            # Exclude all other dunders
            if m_name.startswith("__") and m_name.endswith("__"):
                return False
            # Exclude any name that corresponds to a Pydantic field
            if m_name in pyd_fields:
                return False
            # Exclude attrs field names (prevents slot members from leaking in)
            if m_name in attrs_field_names:
                return False
            # Exclude the sunder names we created for PrivateAttr
            if m_name in private_attr_sunder_names:
                return False
            # Allow instance methods, descriptors, and non-callable constants
            return inspect.isfunction(obj) or _is_descriptor(obj) or (not callable(obj))

        for m_name, obj in inspect.getmembers(_type):
            if _should_include_member(m_name, obj):
                mixin_ns[m_name] = obj

        # Preserve docstring if present
        if getattr(_type, "__doc__", None):
            mixin_ns.setdefault("__doc__", _type.__doc__)

        # Wire __attrs_post_init__ into Pydantic's model_post_init if present
        if hasattr(_type, "__attrs_post_init__"):
            orig_post_init = _type.__attrs_post_init__

            def _model_post_init(self, _orig=orig_post_init):
                # Let attrs post-init run against the Pydantic instance
                _orig(self)

            # only inject if not already provided by the source type
            mixin_ns.setdefault("model_post_init", _model_post_init)

        # Add collected PrivateAttr declarations
        mixin_ns.update(private_attrs)

        base_config = ConfigDict(arbitrary_types_allowed=need_arbitrary_types)
        MethodsMixin = type(
            f"{name}MethodsMixin",
            (BaseModel,),
            {"model_config": base_config, **mixin_ns},
        )

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
