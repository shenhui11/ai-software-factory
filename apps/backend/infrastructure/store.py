from __future__ import annotations

from dataclasses import asdict
from typing import Any

from apps.backend.domain.models import (
    Chapter,
    ChapterVersion,
    ParagraphEditSuggestion,
    QaIssue,
    QaScan,
    StoryCanon,
    StoryOutline,
    StoryProject,
)
from apps.backend.template.models import (
    Template,
    TemplateAuditEvent,
    TemplateCategory,
    TemplateGenerationRecord,
    TemplateTag,
)


class InMemoryStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.projects: dict[str, StoryProject] = {}
        self.canons: dict[str, StoryCanon] = {}
        self.outlines: dict[str, StoryOutline] = {}
        self.chapters: dict[str, Chapter] = {}
        self.versions: dict[str, ChapterVersion] = {}
        self.chapter_versions: dict[str, list[str]] = {}
        self.edit_suggestions: dict[str, ParagraphEditSuggestion] = {}
        self.scans: dict[str, QaScan] = {}
        self.chapter_scans: dict[str, list[str]] = {}
        self.issues: dict[str, QaIssue] = {}
        self.templates: dict[str, Template] = {}
        self.template_categories: dict[str, TemplateCategory] = {}
        self.template_tags: dict[str, TemplateTag] = {}
        self.template_generation_records: dict[str, TemplateGenerationRecord] = {}
        self.template_audit_events: dict[str, TemplateAuditEvent] = {}

    def dump_project_state(self, project_id: str) -> dict[str, Any]:
        project = self.projects[project_id]
        canon = self.canons.get(project_id)
        outline = self.outlines.get(project_id)
        return {
            "project": asdict(project),
            "canon": asdict(canon) if canon else None,
            "outline": asdict(outline) if outline else None,
        }


store = InMemoryStore()
