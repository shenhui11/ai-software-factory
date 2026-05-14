from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class FoundationTaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class UserRole(str, Enum):
    creator = "creator"
    admin = "admin"


def _normalize_genre_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
        return [item for item in items if item]
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            cleaned = str(item).strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized
    return []


class GenreConfig(BaseModel):
    value: str
    label: str
    required_any: list[str] = Field(default_factory=list)
    forbidden_any: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    title: str
    genre: str
    genres: list[str] = Field(default_factory=list)
    length_type: str
    template_id: str = ""
    summary: str
    character_cards: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    event_summary: list[str] = Field(default_factory=list)
    story_beats: list[dict[str, Any]] = Field(default_factory=list)
    mode_default: TaskMode = TaskMode.manual

    @model_validator(mode="before")
    @classmethod
    def _compat_genres(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            genres = _normalize_genre_list(payload.get("genres"))
            genre = str(payload.get("genre", "")).strip()
            if not genres and genre:
                genres = [genre]
            if genres and not genre:
                genre = genres[0]
            payload["genres"] = genres
            payload["genre"] = genre or "fantasy"
            return payload
        return data


class ProjectFoundationRequest(BaseModel):
    title: str
    genre: str = "fantasy"
    genres: list[str] = Field(default_factory=list)
    length_type: str = "long"
    template_id: str | None = None
    summary: str = ""
    character_cards: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    event_summary: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _compat_genres(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            genres = _normalize_genre_list(payload.get("genres"))
            genre = str(payload.get("genre", "")).strip()
            if not genres and genre:
                genres = [genre]
            if genres and not genre:
                genre = genres[0]
            payload["genres"] = genres
            payload["genre"] = genre or "fantasy"
            return payload
        return data


class ProjectFoundationTask(BaseModel):
    id: str
    user_id: str
    status: FoundationTaskStatus
    request: ProjectFoundationRequest
    progress_stage: str = "queued"
    progress_message: str = "等待开始"
    result: dict[str, object] | None = None
    error_message: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


class AuthRegisterRequest(BaseModel):
    username: str
    password: str = Field(min_length=6)
    role: UserRole = UserRole.creator


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class AuthUser(BaseModel):
    id: str
    username: str
    role: UserRole


class AuthSession(BaseModel):
    token: str
    user: AuthUser


class ProjectMemory(BaseModel):
    global_outline: str
    character_cards: list[str]
    character_profiles: list[dict[str, Any]] = Field(default_factory=list)
    relationship_states: list[dict[str, Any]] = Field(default_factory=list)
    world_rules: list[str]
    event_summary: list[str]
    story_beats: list[dict[str, Any]] = Field(default_factory=list)
    active_phase: dict[str, Any] = Field(default_factory=dict)
    chapter_summaries: list[dict[str, Any]] = Field(default_factory=list)
    timeline_nodes: list[dict[str, Any]] = Field(default_factory=list)
    foreshadow_threads: list[dict[str, Any]] = Field(default_factory=list)
    major_events: list[dict[str, Any]] = Field(default_factory=list)
    fact_records: list[dict[str, Any]] = Field(default_factory=list)
    latest_chapter_index: int = 0


class Template(BaseModel):
    id: str
    name: str
    genre: str
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    style_rules: str
    world_template: str
    character_template: str
    outline_template: str
    status: str
    owner_type: str = "system"
    owner_user_id: str | None = None
    owner_username: str | None = None
    usage_count: int = 0

    @model_validator(mode="before")
    @classmethod
    def _compat_genres(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            genres = _normalize_genre_list(payload.get("genres"))
            genre = str(payload.get("genre", "")).strip()
            if not genres and genre:
                genres = [genre]
            if genres and not genre:
                genre = genres[0]
            payload["genres"] = genres
            payload["genre"] = genre or "fantasy"
            return payload
        return data


class MembershipPlan(BaseModel):
    id: str
    name: str
    daily_free_chapters: int
    monthly_free_chapters: int
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def _compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            if "daily_free_chapters" not in payload and "free_chapter_quota" in payload:
                payload["daily_free_chapters"] = payload["free_chapter_quota"]
            if "monthly_free_chapters" not in payload and "monthly_quota" in payload:
                payload["monthly_free_chapters"] = payload["monthly_quota"]
            return payload
        return data

    @property
    def free_chapter_quota(self) -> int:
        return self.daily_free_chapters

    @property
    def monthly_quota(self) -> int:
        return self.monthly_free_chapters


class UserQuota(BaseModel):
    daily_remaining: int
    monthly_remaining: int
    bonus_remaining: int = 0
    last_daily_reset_at: datetime = Field(default_factory=utc_now)
    last_monthly_reset_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def _compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            if "daily_remaining" not in payload:
                payload["daily_remaining"] = 0
            if "bonus_remaining" not in payload and "free_remaining" in payload:
                payload["bonus_remaining"] = payload["free_remaining"]
            return payload
        return data

    @property
    def free_remaining(self) -> int:
        return self.bonus_remaining

    @free_remaining.setter
    def free_remaining(self, value: int) -> None:
        self.bonus_remaining = value


class Order(BaseModel):
    id: str
    plan_id: str
    amount: float
    status: str
    note: str = ""


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
    score_phase_fit: float = 0.0
    phase_fit_hits: list[str] = Field(default_factory=list)
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
    conflict_alerts: list[dict[str, Any]] = Field(default_factory=list)
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
    progress_stage: str = "queued"
    progress_message: str = "等待开始"
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    chapter_ids: list[str] = Field(default_factory=list)


class Project(BaseModel):
    id: str
    user_id: str = ""
    title: str
    genre: str
    genres: list[str] = Field(default_factory=list)
    length_type: str
    template_id: str = ""
    mode_default: TaskMode
    summary: str
    memory: ProjectMemory
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    chapters: list[Chapter] = Field(default_factory=list)
    tasks: list[ChapterTask] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _compat_genres(cls, data: Any) -> Any:
        if isinstance(data, dict):
            payload = dict(data)
            genres = _normalize_genre_list(payload.get("genres"))
            genre = str(payload.get("genre", "")).strip()
            if not genres and genre:
                genres = [genre]
            if genres and not genre:
                genre = genres[0]
            payload["genres"] = genres
            payload["genre"] = genre or "fantasy"
            return payload
        return data


class ChapterTransformRequest(BaseModel):
    instruction: str
    chapter_content: str | None = None
    paragraph: str | None = None


class OutlineOptionUpdateRequest(BaseModel):
    content: str
    core_conflict: str
    key_event: str
    ending_hook: str


class OutlineRegenerateRequest(BaseModel):
    user_idea: str = ""


class ChapterDraftUpdateRequest(BaseModel):
    content: str


class ChapterUpdateRequest(BaseModel):
    title: str


class GenreConfigUpsertRequest(BaseModel):
    label: str
    required_any: list[str] = Field(default_factory=list)
    forbidden_any: list[str] = Field(default_factory=list)


class MembershipPlanUpsertRequest(BaseModel):
    name: str
    daily_free_chapters: int = Field(ge=0)
    monthly_free_chapters: int = Field(ge=0)
    description: str = ""


class OrderUpsertRequest(BaseModel):
    plan_id: str
    amount: float = Field(ge=0)
    status: str
    note: str = ""


class RewriteResult(BaseModel):
    original: str
    updated: str
    diff: list[dict[str, str]]
    consistency_note: str
    chapter_updated: str | None = None


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
