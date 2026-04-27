from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


class TaskMode(str, Enum):
    manual = "manual"
    auto = "auto"


class ChapterStatus(str, Enum):
    pending = "pending"
    outlining = "outlining"
    outline_selected = "outline_selected"
    drafting = "drafting"
    reviewing = "reviewing"
    revising = "revising"
    completed = "completed"
    needs_manual_review = "needs_manual_review"
    confirmed = "confirmed"


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    waiting_user_confirm = "waiting_user_confirm"
    completed = "completed"
    failed = "failed"


class ProjectCreate(BaseModel):
    title: str
    genre: str
    length_type: str
    template_id: str
    summary: str
    character_cards: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    event_summary: list[str] = Field(default_factory=list)
    mode_default: TaskMode = TaskMode.manual


class ProjectMemory(BaseModel):
    global_outline: str
    character_cards: list[str]
    world_rules: list[str]
    event_summary: list[str]
    latest_chapter_index: int = 0


class Template(BaseModel):
    id: str
    name: str
    genre: str
    style_rules: str
    world_template: str
    character_template: str
    outline_template: str
    status: str
    owner_type: str = "system"


class MembershipPlan(BaseModel):
    id: str
    name: str
    free_chapter_quota: int
    monthly_quota: int


class UserQuota(BaseModel):
    free_remaining: int
    monthly_remaining: int


class Order(BaseModel):
    id: str
    plan_id: str
    amount: float
    status: str


class OutlineOption(BaseModel):
    id: str
    option_no: int
    content: str
    core_conflict: str
    key_event: str
    ending_hook: str
    score_plot: float
    score_consistency: float
    score_hook: float
    final_score: float
    editor_comment: str
    selected: bool = False


class ChapterDraft(BaseModel):
    id: str
    revision_no: int
    content: str
    score_readability: float
    score_tension: float
    score_consistency: float
    final_score: float
    issue_summary: str
    selected: bool = False


class Chapter(BaseModel):
    id: str
    chapter_index: int
    title: str
    status: ChapterStatus
    outline_options: list[OutlineOption] = Field(default_factory=list)
    selected_option_id: str | None = None
    drafts: list[ChapterDraft] = Field(default_factory=list)
    final_draft_id: str | None = None
    needs_manual_review: bool = False
    confirmed_by_user: bool = False
    rewrite_count: int = 0


class ChapterTask(BaseModel):
    id: str
    project_id: str
    start_chapter_index: int
    requested_chapter_count: int
    mode: TaskMode
    status: TaskStatus
    current_chapter_index: int
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    chapter_ids: list[str] = Field(default_factory=list)


class Project(BaseModel):
    id: str
    title: str
    genre: str
    length_type: str
    template_id: str
    mode_default: TaskMode
    summary: str
    memory: ProjectMemory
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    chapters: list[Chapter] = Field(default_factory=list)
    tasks: list[ChapterTask] = Field(default_factory=list)


class RewriteRequest(BaseModel):
    paragraph: str
    instruction: str


class RewriteResult(BaseModel):
    original: str
    updated: str
    diff: list[dict[str, str]]
    consistency_note: str


class TaskCreateRequest(BaseModel):
    mode: TaskMode
    chapter_count: int = Field(ge=1, le=10)
    start_chapter_index: int = Field(default=1, ge=1)


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ApiEnvelope(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Any
    request_id: str


class SafetyPolicy(BaseModel):
    id: str
    blocked_terms: list[str]
    copyright_notice: str


class AuditLog(BaseModel):
    id: str
    action: str
    details: dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)
