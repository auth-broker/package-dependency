import os
from typing import Annotated, Literal, Union
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Discriminator

from obo_core.dependency.loaders.environment_object import ObjectLoaderEnvironment


# --- Sample discriminated-subtype models for testing ---
class DummyStoreA(BaseModel):
    type: Literal["A"] = "A"
    foo: str = "default_foo"
    num: int = 1


class DummyStoreB(BaseModel):
    type: Literal["B"] = "B"
    bar: str
    flag: bool = False


LoaderUnion = Annotated[Union[DummyStoreA, DummyStoreB], Discriminator("type")]


@pytest.mark.parametrize(
    "env_overrides, expected_values, expected_instance",
    [
        (
            {
                "DUMMY_STORE_TYPE": "A",
                "DUMMY_STORE_A_FOO": "hello_world",
                "DUMMY_STORE_A_NUM": "42",
            },
            {"type": "A", "foo": "hello_world", "num": "42"},
            DummyStoreA(foo="hello_world", num=42),
        ),
        (
            {
                "DUMMY_STORE_TYPE": "B",
                "DUMMY_STORE_B_BAR": "hello_world",
                "DUMMY_STORE_B_FLAG": "True",
            },
            {"type": "B", "bar": "hello_world", "flag": "True"},
            DummyStoreB(bar="hello_world", flag=True),
        ),
    ],
)
def test_loader_multi_type(env_overrides, expected_values, expected_instance):
    """Selects correct subtype and applies field overrides from env vars."""
    loader = ObjectLoaderEnvironment[LoaderUnion]()

    with patch.dict(os.environ, env_overrides, clear=False):
        result = loader.load()
        assert result == expected_instance


@pytest.mark.parametrize(
    "env_overrides, expected_values, expected_instance",
    [
        (
            {
                "DUMMY_STORE_A_FOO": "hello_world",
                "DUMMY_STORE_A_NUM": "42",
            },
            {"foo": "hello_world", "num": "42"},
            DummyStoreA(foo="hello_world", num=42),
        ),
    ],
)
def test_loader_single_type(env_overrides, expected_values, expected_instance):
    loader = ObjectLoaderEnvironment[DummyStoreA]()

    with patch.dict(os.environ, env_overrides, clear=False):
        result = loader.load()
        assert result == expected_instance
