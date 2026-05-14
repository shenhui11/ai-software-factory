from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

from httpx import ASGITransport, AsyncClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.backend.main import app
from apps.backend.store import InMemoryStore
import apps.backend.main as main_module


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    main_module.store = InMemoryStore()
    main_module.service = main_module.NovelService(main_module.store)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
