import json
from typing import Any

from pydantic_core.core_schema import CoreSchema

COMPLEX_SCHEMA_TYPES = {"list"}


def _clean_field(
    obj: dict[str, Any],
    field_path: list[str] | str,
    *,
    key_delim: str = "_",
) -> None:
    """Remove the branch specified by `field_path`. After deleting the leaf,
    recursively delete any parent keys that become empty dictionaries.

    Parameters
    ----------
    obj : dict
        The dictionary to clean (modified in place).
    field_path : list[str] | str
        Either an iterable of keys, e.g. ["a", "b", "c"],
        or a single string with keys joined by `key_delim`, e.g. "a_b_c".
    key_delim : str, default "_"
        Delimiter to split `field_path` when it is given as a string.

    Examples
    --------
    >>> data = {"a": {"b": 1}, "c": {}}
    >>> _clean_field(data, ["a", "b"])
    >>> data
    {}

    >>> data = {"a": {"b": 1, "c": 2}}
    >>> _clean_field(data, ["a", "b"])
    >>> data
    {'a': {'c': 2}}

    """
    # Normalise the path into a list of keys
    if isinstance(field_path, str):
        path: list[str] = field_path.split(key_delim)
    else:
        path = list(field_path)

    if not path:  # safety-guard: empty path means nothing to do
        return

    key = path[0]

    # Key not present → nothing to delete
    if key not in obj:
        return

    # ────────────────────────
    # 1) Leaf level: delete it
    # ────────────────────────
    if len(path) == 1:
        del obj[key]

    # ────────────────────────────────────────────
    # 2) Recurse further, then prune if now empty
    # ────────────────────────────────────────────
    else:
        child = obj[key]
        if isinstance(child, dict):
            _clean_field(child, path[1:], key_delim=key_delim)
            if not child:  # became empty → delete this branch
                del obj[key]


def _align_field(
    obj: dict[str, Any],
    field_name: str,
    *,
    key_delim: str = "_",
) -> None:
    # scenario 1, the whole key was defined in obj
    if field_name in obj:
        return None

    # scenario 2, each part of the key was defined in obj
    # validate that all parts exist in the obj first, before extracting anything
    field_path = field_name.split(key_delim)
    next_value = obj
    while field_path:
        next_part = field_path.pop(0)
        next_value = next_value.get(next_part)
        if not next_value:
            return None

    # if we made it here, there was a value nested by the broke up field path
    # so we need to perform the cleaning. Since it is nested, there may be
    # other values under the same sub branch, so need to ensuure we don't
    # accidentally delete some overlapping data.
    _clean_field(obj, field_name.split(key_delim))
    obj[field_name] = next_value


def _get_base_schema(schema: CoreSchema):
    while "schema" in schema:
        schema = schema["schema"]
    return schema


def _is_complex_schema(schema: CoreSchema) -> bool:
    base_schema = _get_base_schema(schema)
    base_schema_type = base_schema["type"]
    return base_schema_type in COMPLEX_SCHEMA_TYPES


def _decode_complex_value(value: Any):
    return json.loads(value)


def pydanticize_model_fields(
    obj: dict[str, Any],
    schema: CoreSchema,
    *,
    definition_map: dict | None = None,
    decode_complex_values: bool = True,
) -> dict[str, Any]:
    fields = schema["fields"]
    for field_name, field_schema in fields.items():
        _align_field(obj, field_name)

        if field_name not in obj:
            continue

        obj[field_name] = pydanticize_data(
            obj.pop(field_name),
            field_schema,
            definition_map=definition_map,
            decode_complex_values=decode_complex_values,
        )

    return obj


def pydanticize_model_field(
    obj: dict[str, Any] | Any,
    schema: CoreSchema,
    *,
    definition_map: dict | None = None,
    decode_complex_values: bool = True,
) -> dict[str, Any] | Any:
    if decode_complex_values and _is_complex_schema(schema):
        return _decode_complex_value(obj)

    if obj is not None and "schema" in schema:
        return pydanticize_data(
            obj,
            schema["schema"],
            definition_map=definition_map,
            decode_complex_values=decode_complex_values,
        )

    return obj


def pydanticize_tagged_union(
    obj: dict[str, Any],
    schema: CoreSchema,
    *,
    definition_map: dict | None = None,
    decode_complex_values: bool = True,
) -> dict[str, Any]:
    discriminator = schema["discriminator"]
    discriminator_choice = obj[discriminator]
    if not isinstance(discriminator_choice, str):
        raise TypeError(
            f"Invalid Discriminator Choice. Expected {repr(str)}, found {repr(type(discriminator_choice))}."
        )

    # the name of the field on obj which points to values
    discriminator_values_field = discriminator_choice.lower()

    # apply correction to field for discriminator choice
    _align_field(obj, discriminator_values_field)

    # extract the values and flatten, for pydantic
    if discriminator_values_field in obj:
        discriminator_values = obj.pop(discriminator_choice.lower())
        if not isinstance(discriminator_values, dict):
            raise TypeError(
                f"Invalid Discriminator Body. Expected {repr(dict)}, found {repr(type(discriminator_values))}."
            )
        discriminator_choice_schema = schema["choices"][discriminator_choice]
        pydanticized_body = pydanticize_data(
            discriminator_values,
            discriminator_choice_schema,
            definition_map=definition_map,
            decode_complex_values=decode_complex_values,
        )
        return obj | pydanticized_body

    return obj


def pydanticize_definitions(
    obj: dict[str, Any],
    schema: CoreSchema,
    *,
    definition_map: dict | None = None,
    decode_complex_values: bool = True,
) -> dict[str, Any]:
    if definition_map is None:
        definition_map = {}
    definitions = schema["definitions"]
    for definition in definitions:
        definition_map[definition["ref"]] = definition

    return pydanticize_data(
        obj,
        schema["schema"],
        definition_map=definition_map,
        decode_complex_values=decode_complex_values,
    )


def pydanticize_definition_ref(
    obj: dict[str, Any],
    schema: CoreSchema,
    *,
    definition_map: dict | None = None,
    decode_complex_values: bool = True,
) -> dict[str, Any]:
    schema_ref = schema["schema_ref"]
    schema = definition_map[schema_ref]
    return pydanticize_data(
        obj,
        schema,
        definition_map=definition_map,
        decode_complex_values=decode_complex_values,
    )


def pydanticize_child_schema(
    obj: dict[str, Any],
    schema: CoreSchema,
    *,
    definition_map: dict | None = None,
    decode_complex_values: bool = True,
) -> dict[str, Any]:
    field_schema = schema["schema"]
    return pydanticize_data(
        obj,
        field_schema,
        definition_map=definition_map,
        decode_complex_values=decode_complex_values,
    )


def pydanticize_data(
    obj: dict[str, Any] | Any,
    core_schema: CoreSchema,
    *,
    definition_map: dict | None = None,
    decode_complex_values: bool = True,
) -> dict[str, Any]:
    if definition_map is None:
        definition_map = {}

    if "type" in core_schema:
        type = core_schema["type"]

        if type == "model-field":
            return pydanticize_model_field(
                obj,
                core_schema,
                definition_map=definition_map,
                decode_complex_values=decode_complex_values,
            )
        if type == "model-fields":
            return pydanticize_model_fields(
                obj,
                core_schema,
                definition_map=definition_map,
                decode_complex_values=decode_complex_values,
            )
        if type == "tagged-union":
            return pydanticize_tagged_union(
                obj,
                core_schema,
                definition_map=definition_map,
                decode_complex_values=decode_complex_values,
            )
        if type == "definition-ref":
            return pydanticize_definition_ref(
                obj,
                core_schema,
                definition_map=definition_map,
                decode_complex_values=decode_complex_values,
            )
        if type == "definitions":
            return pydanticize_definitions(
                obj,
                core_schema,
                definition_map=definition_map,
                decode_complex_values=decode_complex_values,
            )

    if "schema" in core_schema:
        return pydanticize_child_schema(
            obj,
            core_schema,
            definition_map=definition_map,
            decode_complex_values=decode_complex_values,
        )

    # already pydanticised
    return obj
