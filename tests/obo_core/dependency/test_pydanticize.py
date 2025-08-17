from typing import Annotated, Literal, Optional, Union

import pytest
from deepdiff import DeepDiff
from pydantic import BaseModel, Discriminator, TypeAdapter

from obo_core.dependency.pydanticize import pydanticize


# 1) define our union types
class A(BaseModel):
    letter: Literal["A"]
    extra: str


class B(BaseModel):
    letter: Literal["B"]
    extra: str


class C(BaseModel):
    letter: Literal["C"]
    extra: str


ABC = Annotated[Union[A, B, C], Discriminator("letter")]


class ABCHierarchy(BaseModel):
    char: ABC
    child: Optional["ABCHierarchy"] = None
    extra: str


class One(BaseModel):
    number: Literal["1"]
    extra: str


class Two(BaseModel):
    number: Literal["2"]
    extra: str


class Three(BaseModel):
    number: Literal["3"]
    extra: str


OneTwoThree = Annotated[Union[One, Two, Three], Discriminator("number")]


class MultiValue1(BaseModel):
    type: Literal["MULTI_VALUE1"]
    extra: str


class MultiValue2(BaseModel):
    type: Literal["MULTI_VALUE2"]
    extra: str


MultiValue = Annotated[Union[MultiValue1, MultiValue2], Discriminator("type")]


class Group(BaseModel):
    char: ABC
    digit: OneTwoThree
    extra: str


class GroupHierarchy(BaseModel):
    group: Group
    child: Optional["GroupHierarchy"] = None
    extra: str


class WithUnderscore(BaseModel):
    some_field: str
    another_value: int


@pytest.mark.parametrize(
    "before,core_schema,after",
    [
        # underscore field case
        (
            {"some": {"field": "hello"}, "another": {"value": 42}},
            TypeAdapter(WithUnderscore).core_schema,
            {"some_field": "hello", "another_value": 42},
        ),
        # single type
        (
            {"type": "MULTI_VALUE1", "multi": {"value1": {"extra": "blah"}}},
            TypeAdapter(MultiValue).core_schema,
            {"type": "MULTI_VALUE1", "extra": "blah"},
        ),
        # single type with multi value
        (
            {"letter": "A", "extra": "blah"},
            TypeAdapter(A).core_schema,
            {"letter": "A", "extra": "blah"},
        ),
        # single‐segment
        (
            {"letter": "A", "a": {"extra": "blah"}},
            TypeAdapter(ABC).core_schema,
            {"letter": "A", "extra": "blah"},
        ),
        # single‐segment-hierarchy
        (
            {
                "char": {"letter": "A", "a": {"extra": "blah"}},
                "child": {
                    "char": {"letter": "B", "b": {"extra": "blah"}},
                    "child": {
                        "char": {"letter": "C", "c": {"extra": "blah"}},
                        "child": None,
                        "extra": "blah",
                    },
                    "extra": "blah",
                },
                "extra": "blah",
            },
            TypeAdapter(ABCHierarchy).core_schema,
            {
                "char": {"letter": "A", "extra": "blah"},
                "child": {
                    "char": {"letter": "B", "extra": "blah"},
                    "child": {
                        "char": {"letter": "C", "extra": "blah"},
                        "child": None,
                        "extra": "blah",
                    },
                    "extra": "blah",
                },
                "extra": "blah",
            },
        ),
        # multi-segment
        (
            {
                "char": {"letter": "A", "a": {"extra": "blah"}},
                "digit": {"number": "1", "1": {"extra": "blah"}},
                "extra": "blah",
            },
            TypeAdapter(Group).core_schema,
            {
                "char": {"letter": "A", "extra": "blah"},
                "digit": {"number": "1", "extra": "blah"},
                "extra": "blah",
            },
        ),
        # multi-segment-hierarchy
        (
            {
                "group": {
                    "char": {"letter": "A", "a": {"extra": "blah"}},
                    "digit": {"number": "1", "1": {"extra": "blah"}},
                    "extra": "blah",
                },
                "child": {
                    "group": {
                        "char": {"letter": "B", "b": {"extra": "blah"}},
                        "digit": {"number": "2", "2": {"extra": "blah"}},
                        "extra": "blah",
                    },
                    "child": {
                        "group": {
                            "char": {"letter": "C", "c": {"extra": "blah"}},
                            "digit": {"number": "3", "3": {"extra": "blah"}},
                            "extra": "blah",
                        },
                        "child": None,
                        "extra": "blah",
                    },
                    "extra": "blah",
                },
                "extra": "blah",
            },
            TypeAdapter(GroupHierarchy).core_schema,
            {
                "group": {
                    "char": {"letter": "A", "extra": "blah"},
                    "digit": {"number": "1", "extra": "blah"},
                    "extra": "blah",
                },
                "child": {
                    "group": {
                        "char": {"letter": "B", "extra": "blah"},
                        "digit": {"number": "2", "extra": "blah"},
                        "extra": "blah",
                    },
                    "child": {
                        "group": {
                            "char": {"letter": "C", "extra": "blah"},
                            "digit": {"number": "3", "extra": "blah"},
                            "extra": "blah",
                        },
                        "child": None,
                        "extra": "blah",
                    },
                    "extra": "blah",
                },
                "extra": "blah",
            },
        ),
    ],
)
def test_flatten_discriminator_all_cases(before, core_schema, after):
    got = pydanticize(before, core_schema)
    diff = DeepDiff(got, after, ignore_order=True)
    assert diff == {}
