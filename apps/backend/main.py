from __future__ import annotations

import logging

from fastapi import FastAPI

from apps.backend.api.errors import register_error_handlers
from apps.backend.api.routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="FEAT-0002 Membership System")
register_error_handlers(app)
app.include_router(router)
