import os
from typing import Annotated, Literal
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Discriminator, ValidationError

from ab_core.dependency.depends import Load


class SimpleListObject(BaseModel):
    list_field: list[str]


class BlahItem(BaseModel):
    type: Literal["blah"] = "blah"
    label: str


class OtherItem(BaseModel):
    type: Literal["other"] = "other"
    label: str


Item = Annotated[BlahItem | OtherItem, Discriminator("type")]


class ObjectWithModelList(BaseModel):
    list_field: list[Item]


class NestedChild(BaseModel):
    name: str
    tags: list[str]


class ObjectWithNestedModelList(BaseModel):
    children: list[NestedChild]


class FalsyConfig(BaseModel):
    zero: int
    false_value: bool
    empty: str


class RequiredConfig(BaseModel):
    required_value: int


def test_list_of_primitives_supports_existing_json_serialised_form():
    with patch.dict(
        os.environ,
        {
            "SIMPLE_LIST_OBJECT_LIST_FIELD": '["A", "B", "C", "D"]',
        },
        clear=False,
    ):
        result = Load(SimpleListObject, persist=False)

    assert result == SimpleListObject(list_field=["A", "B", "C", "D"])


def test_list_of_primitives_supports_indexed_env_form():
    with patch.dict(
        os.environ,
        {
            "SIMPLE_LIST_OBJECT_LIST_FIELD_0": "A",
            "SIMPLE_LIST_OBJECT_LIST_FIELD_1": "B",
            "SIMPLE_LIST_OBJECT_LIST_FIELD_2": "C",
            "SIMPLE_LIST_OBJECT_LIST_FIELD_3": "D",
        },
        clear=False,
    ):
        result = Load(SimpleListObject, persist=False)

    assert result == SimpleListObject(list_field=["A", "B", "C", "D"])


def test_list_json_form_conflicts_with_indexed_form():
    with patch.dict(
        os.environ,
        {
            "SIMPLE_LIST_OBJECT_LIST_FIELD": '["JSON_A", "JSON_B"]',
            "SIMPLE_LIST_OBJECT_LIST_FIELD_0": "INDEXED_A",
            "SIMPLE_LIST_OBJECT_LIST_FIELD_1": "INDEXED_B",
        },
        clear=False,
    ):
        with pytest.raises(RuntimeError, match="Environment variable collision"):
            Load(SimpleListObject, persist=False)


def test_list_of_discriminated_models_supports_indexed_env_form():
    with patch.dict(
        os.environ,
        {
            "OBJECT_WITH_MODEL_LIST_LIST_FIELD_0_TYPE": "blah",
            "OBJECT_WITH_MODEL_LIST_LIST_FIELD_0_BLAH_LABEL": "first",
            "OBJECT_WITH_MODEL_LIST_LIST_FIELD_1_TYPE": "other",
            "OBJECT_WITH_MODEL_LIST_LIST_FIELD_1_OTHER_LABEL": "second",
        },
        clear=False,
    ):
        result = Load(ObjectWithModelList, persist=False)

    assert result == ObjectWithModelList(
        list_field=[
            BlahItem(label="first"),
            OtherItem(label="second"),
        ]
    )


def test_list_of_discriminated_models_supports_json_serialised_form():
    with patch.dict(
        os.environ,
        {
            "OBJECT_WITH_MODEL_LIST_LIST_FIELD": """
            [
                {\"type\": \"blah\", \"label\": \"first\"},
                {\"type\": \"other\", \"label\": \"second\"}
            ]
            """,
        },
        clear=False,
    ):
        result = Load(ObjectWithModelList, persist=False)

    assert result == ObjectWithModelList(
        list_field=[
            BlahItem(label="first"),
            OtherItem(label="second"),
        ]
    )


def test_list_of_nested_models_supports_indexed_env_form():
    with patch.dict(
        os.environ,
        {
            "OBJECT_WITH_NESTED_MODEL_LIST_CHILDREN_0_NAME": "first",
            "OBJECT_WITH_NESTED_MODEL_LIST_CHILDREN_0_TAGS_0": "a",
            "OBJECT_WITH_NESTED_MODEL_LIST_CHILDREN_0_TAGS_1": "b",
            "OBJECT_WITH_NESTED_MODEL_LIST_CHILDREN_1_NAME": "second",
            "OBJECT_WITH_NESTED_MODEL_LIST_CHILDREN_1_TAGS_0": "c",
            "OBJECT_WITH_NESTED_MODEL_LIST_CHILDREN_1_TAGS_1": "d",
        },
        clear=False,
    ):
        result = Load(ObjectWithNestedModelList, persist=False)

    assert result == ObjectWithNestedModelList(
        children=[
            NestedChild(name="first", tags=["a", "b"]),
            NestedChild(name="second", tags=["c", "d"]),
        ]
    )


def test_sparse_indexed_list_raises_validation_error_or_value_error():
    with patch.dict(
        os.environ,
        {
            "SIMPLE_LIST_OBJECT_LIST_FIELD_0": "A",
            "SIMPLE_LIST_OBJECT_LIST_FIELD_2": "C",
        },
        clear=False,
    ):
        with pytest.raises((ValidationError, ValueError)):
            Load(SimpleListObject, persist=False)


def test_empty_json_list_still_supported():
    with patch.dict(
        os.environ,
        {
            "SIMPLE_LIST_OBJECT_LIST_FIELD": "[]",
        },
        clear=False,
    ):
        result = Load(SimpleListObject, persist=False)

    assert result == SimpleListObject(list_field=[])


def test_environment_object_preserves_falsy_values():
    with patch.dict(
        os.environ,
        {
            "FALSY_CONFIG_ZERO": "0",
            "FALSY_CONFIG_FALSE_VALUE": "false",
            "FALSY_CONFIG_EMPTY": "",
        },
        clear=False,
    ):
        result = Load(FalsyConfig, persist=False)

    assert result.zero == 0
    assert result.false_value is False
    assert result.empty == ""


def test_missing_required_env_var_raises_clear_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REQUIRED_CONFIG_REQUIRED_VALUE", raising=False)

    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Load(RequiredConfig, persist=False)

    assert "required_value" in str(exc_info.value)
