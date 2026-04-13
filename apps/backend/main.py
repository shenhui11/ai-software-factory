from __future__ import annotations

import logging

from fastapi import FastAPI

from apps.backend.api.errors import register_error_handlers
from apps.backend.api.member_routes import router as member_router
from apps.backend.api.routes import router
from apps.backend.api.template_routes import router as template_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="FEAT-0001 Story Workbench")
register_error_handlers(app)
app.include_router(router)
app.include_router(member_router)
app.include_router(template_router)
