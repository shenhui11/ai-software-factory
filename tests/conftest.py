from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.backend.infrastructure.store import store
from apps.backend.main import app


class ApiTestClient:
    def __init__(self) -> None:
        self.base_url = "http://test"

    def get(self, path: str, **kwargs) -> httpx.Response:
        return asyncio.run(self._request("GET", path, **kwargs))

    def post(self, path: str, **kwargs) -> httpx.Response:
        return asyncio.run(self._request("POST", path, **kwargs))

    def put(self, path: str, **kwargs) -> httpx.Response:
        return asyncio.run(self._request("PUT", path, **kwargs))

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
            return await client.request(method, path, **kwargs)


@pytest.fixture()
def client() -> ApiTestClient:
    store.reset()
    yield ApiTestClient()


@pytest.fixture()
def user_headers() -> dict[str, str]:
    return {"X-User-Id": "user-1", "X-Role": "user"}


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    return {"X-User-Id": "admin-1", "X-Role": "admin"}
