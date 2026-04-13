from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


MembershipStatus = Literal["regular", "growth_member"]
TaskType = Literal["check_in", "manual"]
LedgerSourceType = Literal["check_in", "task_completion"]
ChangeType = Literal["earn", "spend"]


@dataclass
class LevelRule:
    level_code: str
    level_name: str
    growth_threshold: int
    description: str


@dataclass
class BenefitDefinition:
    benefit_code: str
    title: str
    description: str
    is_enabled: bool = True


@dataclass
class BenefitMapping:
    level_code: str
    benefit_codes: list[str]


@dataclass
class TaskDefinition:
    task_code: str
    title: str
    task_type: TaskType
    reward_points: int
    daily_limit: int
    is_enabled: bool = True


@dataclass
class PublishedConfig:
    version: int
    published_at: datetime
    tasks: dict[str, TaskDefinition]
    levels: list[LevelRule]
    benefits: dict[str, BenefitDefinition]
    benefit_mappings: dict[str, BenefitMapping]


@dataclass
class DraftConfig:
    tasks: dict[str, TaskDefinition] = field(default_factory=dict)
    levels: list[LevelRule] = field(default_factory=list)
    benefits: dict[str, BenefitDefinition] = field(default_factory=dict)
    benefit_mappings: dict[str, BenefitMapping] = field(default_factory=dict)


@dataclass
class MemberProfile:
    user_id: str
    membership_status: MembershipStatus = "regular"
    current_level: str = "L1"
    growth_value: int = 0
    current_config_version: int = 1
    id: str = field(default_factory=lambda: new_id("member"))
    last_level_up_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class PointsAccount:
    user_id: str
    points_balance: int = 0
    points_earned_total: int = 0
    points_spent_total: int = 0
    id: str = field(default_factory=lambda: new_id("points"))
    last_earned_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class TaskRecord:
    user_id: str
    task_code: str
    task_date: str
    progress: int = 0
    status: str = "pending"
    completed_at: datetime | None = None
    request_ids: set[str] = field(default_factory=set)
    id: str = field(default_factory=lambda: new_id("task_record"))


@dataclass
class LedgerEntry:
    user_id: str
    request_id: str
    source_type: LedgerSourceType
    source_ref_id: str
    change_type: ChangeType
    points_delta: int
    balance_after: int
    id: str = field(default_factory=lambda: new_id("ledger"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class RewardRecord:
    user_id: str
    request_id: str
    reward_type: str
    reward_code: str
    title: str
    context: dict[str, str]
    id: str = field(default_factory=lambda: new_id("reward"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class AuditEvent:
    actor_user_id: str
    actor_role: str
    action: str
    request_id: str
    details: dict[str, str]
    id: str = field(default_factory=lambda: new_id("audit"))
    created_at: datetime = field(default_factory=utc_now)
