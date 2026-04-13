from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from apps.backend.domain.models import new_id, utc_now


MembershipStatus = Literal["regular", "growth_member"]
RewardType = Literal["level_up", "task_completion", "check_in"]
LedgerChangeType = Literal["earn", "spend"]
TaskType = Literal["daily_check_in", "action", "streak"]


@dataclass
class MemberProfile:
    user_id: str
    membership_status: MembershipStatus = "regular"
    current_level: int = 1
    growth_value: int = 0
    last_level_up_at: datetime | None = None
    current_config_version: int = 1
    id: str = field(default_factory=lambda: new_id("member"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class PointsAccount:
    user_id: str
    points_balance: int = 0
    points_earned_total: int = 0
    points_spent_total: int = 0
    last_earned_at: datetime | None = None
    id: str = field(default_factory=lambda: new_id("points"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class PointsLedgerEntry:
    user_id: str
    source_type: str
    source_ref_id: str | None
    change_type: LedgerChangeType
    points_delta: int
    balance_after: int
    request_id: str
    id: str = field(default_factory=lambda: new_id("ledger"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class RewardRecord:
    user_id: str
    reward_type: RewardType
    reward_code: str
    message: str
    request_id: str
    id: str = field(default_factory=lambda: new_id("reward"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class MemberEvent:
    user_id: str
    event_type: str
    request_id: str
    details: dict[str, object]
    actor_id: str
    id: str = field(default_factory=lambda: new_id("event"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class UserTaskState:
    user_id: str
    task_code: str
    completed_today: int = 0
    total_completed: int = 0
    last_completed_on: date | None = None
    last_request_id: str | None = None
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class MemberTaskConfig:
    task_code: str
    title: str
    task_type: TaskType
    reward_points: int
    enabled: bool = True
    daily_limit: int = 1


@dataclass
class LevelConfig:
    level: int
    name: str
    growth_threshold: int
    description: str


@dataclass
class BenefitConfig:
    benefit_code: str
    name: str
    description: str
    enabled: bool = True


@dataclass
class BenefitMapping:
    level: int
    benefit_code: str


@dataclass
class MemberConfigSnapshot:
    version: int
    published_at: datetime | None
    tasks: list[MemberTaskConfig]
    levels: list[LevelConfig]
    benefits: list[BenefitConfig]
    mappings: list[BenefitMapping]

