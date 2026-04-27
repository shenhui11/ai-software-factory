from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.backend.main import app
from apps.backend.store import InMemoryStore
import apps.backend.main as main_module


@pytest.fixture()
def client() -> TestClient:
    main_module.store = InMemoryStore()
    main_module.service = main_module.NovelService(main_module.store)
    return TestClient(app)
