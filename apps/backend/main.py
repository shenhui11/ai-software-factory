from __future__ import annotations

import logging

from fastapi import FastAPI

from apps.backend.api.errors import register_error_handlers
from apps.backend.api.member_routes import router as member_router
from apps.backend.api.routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AI Software Factory Backend")
register_error_handlers(app)
app.include_router(router)
app.include_router(member_router)
