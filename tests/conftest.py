import os

import pytest


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    # Clear relevant env vars before each test
    for var in list(os.environ):
        if var.startswith("DUMMY_"):
            monkeypatch.delenv(var, raising=False)
    yield


__all__ = [
    clear_env,
]
