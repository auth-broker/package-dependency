import inspect
import os
import re
from collections.abc import Iterator
from typing import get_args


def str_intersection(*args: str) -> str:
    if not args:
        return ""

    # use the shortest string as base for substrings
    shortest = min(args, key=len)
    max_len = len(shortest)

    for length in range(max_len, 0, -1):  # longest to shortest
        for start in range(max_len - length + 1):
            candidate = shortest[start : start + length]
            if all(candidate in other for other in args):
                return candidate
    return ""


def type_name_intersection(types: tuple[type, ...]) -> str:
    return str_intersection(*(t.__name__ for t in types))


def to_env_prefix(name: str) -> str:
    """Convert CamelCase or PascalCase to ENV_VAR_STYLE (uppercase with underscores).
    E.g. 'OAuth2TokenStore' -> 'OAUTH2_TOKEN_STORE'
    """
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.upper()


def insert_nested(dct, keys, value):
    for key in keys[:-1]:
        dct = dct.setdefault(key.lower(), {})
    dct[keys[-1].lower()] = value


def apply_suffix(key: str, suffix: str):
    if not key.endswith(suffix):
        return key + suffix
    return key


def extract_discriminator_from_env(
    prefix: str,
    discriminator_key: str,
):
    prefix_with_ = apply_suffix(prefix, "_")
    discriminator_env_key = f"{prefix_with_}{discriminator_key.upper()}"
    discriminator_value = os.environ.get(discriminator_env_key)

    return discriminator_value


def extract_env_tree(env: dict[str, str], prefix: str) -> dict:
    def insert_recursive(current: dict, keys: list[str], value: str):
        key = keys[0].lower()
        if len(keys) == 1:
            current[key] = value
        else:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            insert_recursive(current[key], keys[1:], value)

    result = {}

    env_prefix = prefix if prefix.endswith("_") else prefix + "_"
    prefix_len = len(env_prefix)

    for full_key, value in env.items():
        if full_key.startswith(env_prefix):
            key_suffix = full_key[prefix_len:]
            keys = key_suffix.split("_")
            insert_recursive(result, keys, value)

    return result


def walk_types_args(t_base: type):
    def walk(t):
        yield t

        t_args = get_args(t)

        for t_arg in t_args:
            yield from walk(t_arg)

    yield from walk(t_base)


def extract_target_types(obj: type, target_type: type) -> Iterator[type | object]:
    for t in walk_types_args(obj):
        if isinstance(t, target_type) or isinstance(t, type) and issubclass(t, target_type):
            yield t


def is_real_callable(obj) -> bool:
    """True for user code we actually want to execute as a loader.
    False for typing constructs (Union, Annotated, etc.) that merely
    *happen* to be callable.
    """
    # 1. Plain Python function / lambda / bound method.
    if inspect.isfunction(obj) or inspect.ismethod(obj):
        return True

    # 2. Generator / coroutine / async‑gen functions.
    if inspect.iscoroutinefunction(obj) or inspect.isgeneratorfunction(obj) or inspect.isasyncgenfunction(obj):
        return True

    return False
