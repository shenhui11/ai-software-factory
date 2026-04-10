from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
