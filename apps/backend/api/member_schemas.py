from __future__ import annotations

from pydantic import BaseModel, Field


class TaskConfigPayload(BaseModel):
    task_code: str
    title: str
    task_type: str
    reward_points: int = Field(ge=0)
    enabled: bool = True
    daily_limit: int = Field(default=1, ge=1)


class LevelConfigPayload(BaseModel):
    level: int = Field(ge=1)
    name: str
    growth_threshold: int = Field(ge=0)
    description: str


class BenefitConfigPayload(BaseModel):
    benefit_code: str
    name: str
    description: str
    enabled: bool = True


class BenefitMappingPayload(BaseModel):
    level: int = Field(ge=1)
    benefit_code: str


class UpdateTasksRequest(BaseModel):
    tasks: list[TaskConfigPayload]


class UpdateLevelsRequest(BaseModel):
    levels: list[LevelConfigPayload]


class UpdateBenefitsRequest(BaseModel):
    benefits: list[BenefitConfigPayload]
    mappings: list[BenefitMappingPayload]
