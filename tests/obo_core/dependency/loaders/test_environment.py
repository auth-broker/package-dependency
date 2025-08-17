import os
from unittest.mock import patch

import pytest

from obo_core.dependency.loaders.environment import LoaderEnvironment


@pytest.mark.parametrize(
    "env_overrides, type_, key, expected_raw, expected_casted",
    [
        ({"SOME_KEY": "hello world"}, str, "SOME_KEY", "hello world", "hello world"),
        ({"NUMBER_KEY": "123"}, int, "NUMBER_KEY", "123", 123),
        ({"BOOL_KEY": "true"}, bool, "BOOL_KEY", "true", True),
        ({"FLOAT_KEY": "3.14"}, float, "FLOAT_KEY", "3.14", 3.14),
    ],
)
def test_loader_environment(env_overrides, type_, key, expected_raw, expected_casted):
    loader = LoaderEnvironment[type_](key=key)

    with patch.dict(os.environ, env_overrides, clear=False):
        result_casted = loader.load()
        assert result_casted == expected_casted
