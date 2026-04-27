from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.backend.main import app
from apps.backend.store import InMemoryStore
import apps.backend.main as main_module


@pytest.fixture()
def client() -> TestClient:
    main_module.store = InMemoryStore()
    main_module.service = main_module.NovelService(main_module.store)
    return TestClient(app)
