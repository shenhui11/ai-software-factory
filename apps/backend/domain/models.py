from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass
class StoryProject:
    title: str
    genre: str
    style: str
    target_audience: str
    length_target: str
    tone: str
    premise: str
    id: str = field(default_factory=lambda: new_id("proj"))
    status: str = "draft"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class CharacterProfile:
    name: str
    role: str
    personality_traits: list[str]
    speech_style: str
    motivation: str
    key_relationships: list[str]
    notes: str
    id: str = field(default_factory=lambda: new_id("char"))


@dataclass
class StoryCanon:
    project_id: str
    world_summary: str = ""
    style_constraints: list[str] = field(default_factory=list)
    narrative_rules: list[str] = field(default_factory=list)
    characters: list[CharacterProfile] = field(default_factory=list)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class OutlineChapterItem:
    sequence_no: int
    title: str
    summary: str
    goal: str
    status: str = "planned"
    id: str = field(default_factory=lambda: new_id("outline_ch"))


@dataclass
class StoryOutline:
    project_id: str
    logline: str
    core_conflict: str
    character_summaries: list[str]
    chapters: list[OutlineChapterItem]
    id: str = field(default_factory=lambda: new_id("outline"))
    outline_version: int = 1
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ChapterVersion:
    chapter_id: str
    source_type: Literal[
        "manual_edit",
        "draft_generation",
        "paragraph_edit",
        "qa_fix",
        "restore",
        "snapshot",
    ]
    source_ref_id: str | None
    content: str
    author_type: Literal["user", "system"]
    version_note: str
    id: str = field(default_factory=lambda: new_id("ver"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Chapter:
    project_id: str
    title: str
    summary: str
    outline_item_id: str | None
    id: str = field(default_factory=lambda: new_id("chapter"))
    current_version_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class ParagraphEditSuggestion:
    chapter_id: str
    base_version_id: str
    selection_start: int
    selection_end: int
    operation: str
    instruction: str
    candidate_content: str
    id: str = field(default_factory=lambda: new_id("edit"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class QaIssue:
    scan_id: str
    chapter_id: str
    issue_type: str
    severity: str
    title: str
    description: str
    evidence_excerpt: str
    suggested_fix: str
    start_offset: int
    end_offset: int
    id: str = field(default_factory=lambda: new_id("issue"))


@dataclass
class QaScan:
    chapter_id: str
    base_version_id: str
    status: str
    summary: str
    issues: list[QaIssue]
    id: str = field(default_factory=lambda: new_id("scan"))
    created_at: datetime = field(default_factory=utc_now)


MembershipStatus = Literal["regular", "growth_member"]
TaskType = Literal["check_in", "manual_action", "streak"]
TaskStatus = Literal["pending", "completed", "blocked"]
ChangeType = Literal["earn", "spend"]


@dataclass
class MemberProfile:
    user_id: str
    membership_status: MembershipStatus = "regular"
    current_level: str = "level_1"
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
class MemberTaskConfig:
    task_code: str
    task_type: TaskType
    title: str
    description: str
    is_enabled: bool
    reward_points: int
    daily_limit: int
    window_rule: str
    trigger_source: str
    config_version: int
    id: str = field(default_factory=lambda: new_id("taskcfg"))
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class MemberTaskRecord:
    user_id: str
    task_code: str
    task_date: date
    progress: int = 0
    status: TaskStatus = "pending"
    completed_at: datetime | None = None
    request_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("taskrec"))


@dataclass
class PointsLedgerEntry:
    user_id: str
    source_type: str
    source_ref_id: str
    change_type: ChangeType
    points_delta: int
    balance_after: int
    request_id: str
    details: dict[str, object]
    id: str = field(default_factory=lambda: new_id("ledger"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class LevelConfig:
    code: str
    name: str
    growth_threshold: int
    description: str


@dataclass
class BenefitConfig:
    benefit_code: str
    level_code: str
    name: str
    description: str
    is_enabled: bool
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class RewardRecord:
    user_id: str
    reward_type: str
    reward_code: str
    title: str
    details: dict[str, object]
    request_id: str
    id: str = field(default_factory=lambda: new_id("reward"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class MemberAuditEvent:
    user_id: str
    event_type: str
    request_id: str
    details: dict[str, object]
    operator_user_id: str | None = None
    operator_role: str | None = None
    id: str = field(default_factory=lambda: new_id("audit"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class MemberConfigSnapshot:
    version: int
    tasks: list[MemberTaskConfig]
    levels: list[LevelConfig]
    benefits: list[BenefitConfig]
    published_at: datetime | None = None
    updated_at: datetime = field(default_factory=utc_now)
