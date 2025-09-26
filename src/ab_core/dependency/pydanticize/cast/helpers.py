"""Helpers for casting objects to Pydantic models using type plugins."""

import inspect
from functools import cache
from pydantic import TypeAdapter, BaseModel
from .adaptors.base import BaseTypePlugin
from .adaptors.attrs import AttrsPlugin, HAS_ATTRS


PLUGINS: list[BaseTypePlugin] = []
if HAS_ATTRS:
    PLUGINS.append(AttrsPlugin())


def lookup_plugin(obj: object) -> BaseTypePlugin | None:
    """Find a plugin that can handle the given object."""
    for plugin in PLUGINS:
        if plugin.matches(obj):
            return plugin

    raise ValueError(f"No plugin found for object of type {type(obj)}")


def TryTypeAdapter(_type: object) -> TypeAdapter | Exception:
    """Try to create a TypeAdapter for the given type.

    Returns:
        A TypeAdapter if the type is supported by Pydantic, else None.

    """
    try:
        return TypeAdapter(_type)
    except Exception as e:
        return e

@cache
def cached_type_adapter(_type: object) -> TypeAdapter:
    """Get a cached TypeAdapter or the exception if the type is not supported by Pydantic."""
    # We do this since we can cache that a TypeAdapter cannot be created for a type
    # we we often use to verify if a type is supported by Pydantic
    type_adaptor = TryTypeAdapter(_type)
    if isinstance(type_adaptor, Exception):
        raise type_adaptor
    return type_adaptor


def is_supported_by_pydantic(_type: object) -> bool:
    """Check if the given type is supported by Pydantic."""
    try:
        cached_type_adapter(_type)
        return True
    except Exception:
        return False


@cache
def pydanticize_type(_type: object) -> type:
    """Convert an type to a Pydantic-compatible type.

    Raises:
        TypeError: If the object cannot be converted to a Pydantic-compatible type.
        RuntimeError: If a plugin fails to convert the type.

    """
    # 1. try pydantic native support for the object
    try:
        cached_type_adapter(_type)
        return _type
    except Exception:
        pass

    # 2. try pydantic support via type plugins
    try:
        plugin = lookup_plugin(_type)
    except ValueError as e:
        raise TypeError(
            f"Type {repr(_type)} is not supported by pydantic or any available type plugins."
        ) from e

    # 22.1 upgrade the type using the plugin
    try:
        upgraded_type = plugin.upgrade(_type)
    except Exception as e:
        raise RuntimeError(
            f"Type {repr(_type)} could not be converted to a Pydantic model by plugin {plugin.__class__.__name__}."
        ) from e

    # 2.2 verify that the upgraded type is a Pydantic model
    try:
        cached_type_adapter(upgraded_type)
        return upgraded_type
    except Exception:
        pass

    # 3. if all else fails, raise an error
    raise TypeError(
        f"Type {repr(_type)} was converted to {repr(upgraded_type)}, but the result is not valid for pydantic."
    )


def pydanticize_object(obj: object) -> type:
    """Convert an object or type to a Pydantic-compatible type."""
    # 1. retrieve the type if an instance was given
    _type = obj
    if not inspect.isclass(obj):
        _type = type(obj)

    return pydanticize_type(_type)
