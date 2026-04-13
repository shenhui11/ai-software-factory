from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    error: dict[str, object]
    request_id: str


class TaskConfigPayload(BaseModel):
    task_code: str
    title: str
    task_type: Literal["check_in", "manual"]
    reward_points: int = Field(ge=0)
    daily_limit: int = Field(ge=1)
    is_enabled: bool


class LevelConfigPayload(BaseModel):
    level_code: str
    level_name: str
    growth_threshold: int = Field(ge=0)
    description: str


class BenefitConfigPayload(BaseModel):
    benefit_code: str
    title: str
    description: str
    is_enabled: bool


class BenefitMappingPayload(BaseModel):
    level_code: str
    benefit_codes: list[str]


class UpdateTasksRequest(BaseModel):
    tasks: list[TaskConfigPayload]


class UpdateLevelsRequest(BaseModel):
    levels: list[LevelConfigPayload]


class UpdateBenefitsRequest(BaseModel):
    benefits: list[BenefitConfigPayload]
    mappings: list[BenefitMappingPayload]


class PublishConfigResponse(BaseModel):
    version: int
    published_at: datetime
