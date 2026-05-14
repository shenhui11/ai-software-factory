import os
import sys
from collections.abc import Generator

import anyio
import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("APP_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("AUTH_STORAGE_BACKEND", "sqlite")

from apps.backend.main import app, auth_store
from apps.backend.store import InMemoryStore, store


class SyncASGIClient:
    def __init__(self, app_instance) -> None:
        self._app = app_instance
        self._base_url = "http://testserver"

    async def _request_async(self, method: str, path: str, **kwargs):
        transport = httpx.ASGITransport(app=self._app)
        async with httpx.AsyncClient(transport=transport, base_url=self._base_url) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method: str, path: str, **kwargs):
        async def runner():
            return await self._request_async(method, path, **kwargs)

        return anyio.run(runner)

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs):
        return self.request("PATCH", path, **kwargs)


@pytest.fixture(autouse=True)
def reset_store() -> Generator[None, None, None]:
    original_codex_api_key = os.environ.get("CODEX_API_KEY")
    original_codex_base_url = os.environ.get("CODEX_BASE_URL")
    original_codex_model = os.environ.get("CODEX_MODEL")
    os.environ["CODEX_API_KEY"] = ""
    os.environ["CODEX_BASE_URL"] = "http://127.0.0.1:8000/v1"
    os.environ["CODEX_MODEL"] = "test-model"
    if hasattr(store, "reset_for_tests"):
        store.reset_for_tests()
    fresh = InMemoryStore()
    store.projects = fresh.projects
    store.templates = fresh.templates
    store.membership_plans = fresh.membership_plans
    store.active_plan_id = fresh.active_plan_id
    store.user_quota = fresh.user_quota
    store.orders = fresh.orders
    store.safety_policy = fresh.safety_policy
    store.audit_logs = fresh.audit_logs
    auth_store.reset_for_tests()
    yield
    if original_codex_api_key is None:
        os.environ.pop("CODEX_API_KEY", None)
    else:
        os.environ["CODEX_API_KEY"] = original_codex_api_key
    if original_codex_base_url is None:
        os.environ.pop("CODEX_BASE_URL", None)
    else:
        os.environ["CODEX_BASE_URL"] = original_codex_base_url
    if original_codex_model is None:
        os.environ.pop("CODEX_MODEL", None)
    else:
        os.environ["CODEX_MODEL"] = original_codex_model


@pytest.fixture
def test_client() -> Generator[SyncASGIClient, None, None]:
    yield SyncASGIClient(app)


@pytest.fixture
def client(test_client) -> Generator[SyncASGIClient, None, None]:
    yield test_client


@pytest.fixture
async def async_client() -> Generator[httpx.AsyncClient, None, None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def headers():
    return {
        "Content-Type": "application/json",
        "Authorization": "Bearer test-token",
    }


@pytest.fixture
def admin_headers(headers):
    client = SyncASGIClient(app)
    client.post(
        "/api/auth/register",
        json={"username": "fixture_admin", "password": "secret123", "role": "admin"},
    )
    logged_in = client.post(
        "/api/auth/login",
        json={"username": "fixture_admin", "password": "secret123"},
    )
    token = logged_in.json()["data"]["token"]
    return {
        **headers,
        "Authorization": f"Bearer {token}",
    }
