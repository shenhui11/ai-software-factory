from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CharacterProfilePayload(BaseModel):
    name: str
    role: str
    personality_traits: list[str]
    speech_style: str
    motivation: str
    key_relationships: list[str]
    notes: str


class ProjectCreateRequest(BaseModel):
    title: str
    genre: str
    style: str
    target_audience: str
    length_target: str
    tone: str
    premise: str


class ProjectPatchRequest(BaseModel):
    title: str | None = None
    genre: str | None = None
    style: str | None = None
    target_audience: str | None = None
    length_target: str | None = None
    tone: str | None = None
    premise: str | None = None


class CanonRequest(BaseModel):
    world_summary: str
    style_constraints: list[str]
    narrative_rules: list[str]
    characters: list[CharacterProfilePayload]


class ChapterCreateRequest(BaseModel):
    outline_item_id: str | None = None
    title: str
    summary: str


class ChapterDraftRequest(BaseModel):
    chapter_goal: str
    context_window_strategy: str


class ChapterPatchRequest(BaseModel):
    content: str


class ParagraphEditRequest(BaseModel):
    selection_start: int
    selection_end: int
    operation: Literal[
        "rewrite",
        "expand",
        "compress",
        "tone_shift",
        "style_shift",
    ]
    instruction: str = ""


class FixRange(BaseModel):
    start: int
    end: int


class IssueFixRequest(BaseModel):
    strategy: str
    allowed_range: FixRange


class SnapshotRequest(BaseModel):
    version_note: str = Field(min_length=1)


class ErrorEnvelope(BaseModel):
    error: dict[str, object]
    request_id: str


class VersionDiffResponse(BaseModel):
    version_id: str
    base_version_id: str
    diff: list[str]


class ExportResponse(BaseModel):
    format: str
    content: str


class MetadataResponse(BaseModel):
    id: str
    created_at: datetime
