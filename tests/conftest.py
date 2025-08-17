import os

import pytest
from ab_test.fixtures.database.conftest import (
    tmp_database_async,
    tmp_database_async_session,
    tmp_database_sync,
    tmp_database_sync_session,
)


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    # Clear relevant env vars before each test
    for var in list(os.environ):
        if var.startswith("DUMMY_"):
            monkeypatch.delenv(var, raising=False)
    yield


__all__ = [
    tmp_database_async,
    tmp_database_async_session,
    tmp_database_sync,
    tmp_database_sync_session,
    clear_env,
]
