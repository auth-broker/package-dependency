"""
FastAPI integration-tests for ab_core.dependency.inject
— no module-level global state, endpoints use FastAPI’s Depends.
"""

from typing import Annotated, Dict, Tuple

import pytest
from fastapi import Depends as FDepends
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

# your DI helpers stay available for *internal* deps
from ab_core.dependency import Depends, inject, sentinel


# ------------------------------------------------------------------ #
# Shared request / response helpers                                  #
# ------------------------------------------------------------------ #
class SomeRequest(BaseModel):
    name: str


class SomeDependency(BaseModel):
    value: str = "injected"


def provide_some_dependency() -> SomeDependency:  # <─ FastAPI provider
    return SomeDependency()


def _check_ok(resp):
    assert resp.status_code == 200, f"{resp.status_code=}, body={resp.text}"
    assert resp.json() == {
        "request_name": "TestName",
        "dependency_value": "injected",
    }


# ------------------------------------------------------------------ #
# Fixture: build app + trackers dynamically                           #
# ------------------------------------------------------------------ #
def _build_app() -> Tuple[TestClient, Dict[str, int], Dict[str, int]]:
    """
    Build a fresh FastAPI app *and* per-test trackers.

    Returns
    -------
    client          : TestClient
    sync_tracker    : {"closed": int, "caught": Exception|None}
    async_tracker   : same schema as sync_tracker
    """
    sync_tracker = {"closed": 0, "caught": None}
    async_tracker = {"closed": 0, "caught": None}

    # ---- dependency helpers (still use your DI) ------------------ #
    @inject
    def some_context(
        dependency: Annotated[SomeDependency, Depends(provide_some_dependency)] = sentinel(),
    ):
        try:
            yield dependency
        except Exception as exc:
            sync_tracker["caught"] = exc
            raise
        finally:
            sync_tracker["closed"] += 1

    @inject
    async def some_context_async(
        dependency: Annotated[SomeDependency, Depends(SomeDependency)] = sentinel(),
    ):
        try:
            yield dependency
        except Exception as exc:
            async_tracker["caught"] = exc
            raise
        finally:
            async_tracker["closed"] += 1

    # ---- FastAPI app & routes (plain handlers) ------------------- #
    app = FastAPI()

    @app.post("/items/context")
    def create_item_with_context(
        request: SomeRequest,
        dependency: Annotated[SomeDependency, FDepends(some_context)] = sentinel(),
    ):
        assert sync_tracker["closed"] == 0
        return {"request_name": request.name, "dependency_value": dependency.value}

    @app.post("/items/context/async")
    async def create_item_with_context_async(
        request: SomeRequest,
        dependency: Annotated[SomeDependency, FDepends(some_context_async)] = sentinel(),
    ):
        assert async_tracker["closed"] == 0
        return {"request_name": request.name, "dependency_value": dependency.value}

    # error routes --------------------------------------------------
    @app.post("/items/context/error")
    def create_item_with_context_error(
        request: SomeRequest,
        dependency: Annotated[SomeDependency, FDepends(some_context)] = sentinel(),
    ):
        raise RuntimeError("boom")

    @app.post("/items/context/async/error")
    async def create_item_with_context_async_error(
        request: SomeRequest,
        dependency: Annotated[SomeDependency, FDepends(some_context_async)] = sentinel(),
    ):
        raise RuntimeError("kaboom")

    return TestClient(app), sync_tracker, async_tracker


# ------------------------------------------------------------------ #
# Pytest fixtures                                                    #
# ------------------------------------------------------------------ #
@pytest.fixture
def client_and_trackers():
    return _build_app()


@pytest.fixture
def client(client_and_trackers):
    return client_and_trackers[0]


def test_fastapi_context_dependency(client_and_trackers):
    client, sync_t, _ = client_and_trackers
    _check_ok(client.post("/items/context", json={"name": "TestName"}))
    assert sync_t == {"closed": 1, "caught": None}


def test_fastapi_async_context_dependency(client_and_trackers):
    client, _, async_t = client_and_trackers
    _check_ok(client.post("/items/context/async", json={"name": "TestName"}))
    assert async_t == {"closed": 1, "caught": None}


def test_fastapi_context_dependency_error(client_and_trackers):
    client, sync_t, _ = client_and_trackers
    with pytest.raises(RuntimeError):
        client.post("/items/context/error", json={"name": "TestName"})
    assert sync_t["closed"] == 1 and isinstance(sync_t["caught"], RuntimeError)


def test_fastapi_async_context_dependency_error(client_and_trackers):
    client, _, async_t = client_and_trackers
    with pytest.raises(RuntimeError):
        client.post("/items/context/async/error", json={"name": "TestName"})
    assert async_t["closed"] == 1 and isinstance(async_t["caught"], RuntimeError)
