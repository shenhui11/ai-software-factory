from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MemberTaskConfigPayload(BaseModel):
    task_code: str = Field(min_length=1)
    task_type: Literal["check_in", "manual_action", "streak"]
    title: str = Field(min_length=1)
    description: str = ""
    is_enabled: bool
    reward_points: int = Field(ge=0)
    daily_limit: int = Field(ge=1)
    window_rule: str = "daily"
    trigger_source: str = "manual"


class LevelConfigPayload(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    growth_threshold: int = Field(ge=0)
    description: str = ""


class BenefitConfigPayload(BaseModel):
    benefit_code: str = Field(min_length=1)
    level_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    is_enabled: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskConfigUpdateRequest(BaseModel):
    tasks: list[MemberTaskConfigPayload]


class LevelConfigUpdateRequest(BaseModel):
    levels: list[LevelConfigPayload]


class BenefitConfigUpdateRequest(BaseModel):
    benefits: list[BenefitConfigPayload]
