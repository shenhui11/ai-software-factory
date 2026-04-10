from __future__ import annotations

import difflib
import logging
from dataclasses import asdict

from apps.backend.domain.models import (
    Chapter,
    ChapterVersion,
    CharacterProfile,
    OutlineChapterItem,
    ParagraphEditSuggestion,
    QaIssue,
    QaScan,
    StoryCanon,
    StoryOutline,
    StoryProject,
    utc_now,
)
from apps.backend.infrastructure.store import store

logger = logging.getLogger(__name__)

ALLOWED_EDIT_OPERATIONS = {
    "rewrite",
    "expand",
    "compress",
    "tone_shift",
    "style_shift",
}
ALLOWED_EXPORT_FORMATS = {"md", "txt"}
QA_ISSUE_TYPES = [
    "logic_gap",
    "canon_conflict",
    "plot_discontinuity",
    "redundancy",
    "foreshadowing_miss",
    "voice_drift",
]


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code


def _get_project(project_id: str) -> StoryProject:
    project = store.projects.get(project_id)
    if project is None:
        raise DomainError("project_not_found", "Project not found.", status_code=404)
    return project


def _get_chapter(chapter_id: str) -> Chapter:
    chapter = store.chapters.get(chapter_id)
    if chapter is None:
        raise DomainError("chapter_not_found", "Chapter not found.", status_code=404)
    return chapter


def _get_version(version_id: str) -> ChapterVersion:
    version = store.versions.get(version_id)
    if version is None:
        raise DomainError("version_not_found", "Version not found.", status_code=404)
    return version


def _get_issue(issue_id: str) -> QaIssue:
    issue = store.issues.get(issue_id)
    if issue is None:
        raise DomainError("issue_not_found", "QA issue not found.", status_code=404)
    return issue


def _current_content(chapter: Chapter) -> str:
    if chapter.current_version_id is None:
        return ""
    return _get_version(chapter.current_version_id).content


def _validate_selection(content: str, start: int, end: int) -> str:
    if start < 0 or end > len(content) or start >= end:
        raise DomainError(
            "invalid_selection",
            "Selection range is invalid.",
            details={"selection_start": start, "selection_end": end},
            status_code=400,
        )
    selected = content[start:end]
    if not selected.strip():
        raise DomainError(
            "empty_selection",
            "Selection must contain non-whitespace content.",
            status_code=400,
        )
    return selected


def create_project(payload: dict[str, str]) -> StoryProject:
    project = StoryProject(**payload)
    store.projects[project.id] = project
    store.canons[project.id] = StoryCanon(project_id=project.id)
    logger.info("project_created", extra={"project_id": project.id})
    return project


def get_project(project_id: str) -> StoryProject:
    return _get_project(project_id)


def update_project(project_id: str, payload: dict[str, str]) -> StoryProject:
    project = _get_project(project_id)
    for key, value in payload.items():
        setattr(project, key, value)
    project.updated_at = utc_now()
    return project


def get_or_update_canon(
    project_id: str,
    payload: dict[str, object] | None = None,
) -> StoryCanon:
    _get_project(project_id)
    canon = store.canons[project_id]
    if payload is None:
        return canon
    canon.world_summary = str(payload["world_summary"])
    canon.style_constraints = list(payload["style_constraints"])
    canon.narrative_rules = list(payload["narrative_rules"])
    canon.characters = [
        CharacterProfile(**character)
        for character in list(payload["characters"])
    ]
    canon.updated_at = utc_now()
    return canon


def generate_outline(project_id: str) -> StoryOutline:
    project = _get_project(project_id)
    canon = store.canons[project_id]
    character_summaries = [
        f"{character.name}: {character.role}, {character.motivation}"
        for character in canon.characters
    ] or [f"Primary cast fits the {project.genre} premise."]
    chapters = [
        OutlineChapterItem(
            sequence_no=index,
            title=f"Chapter {index}: {goal}",
            summary=f"{project.tone}推进 {goal.lower()}",
            goal=goal,
        )
        for index, goal in enumerate(
            ["Setup", "Complication", "Decision", "Consequence"], start=1
        )
    ]
    outline = StoryOutline(
        project_id=project.id,
        logline=(
            f"A {project.style} {project.genre} story where "
            f"{project.premise.lower().rstrip('。.')}"
        ),
        core_conflict=(
            f"The protagonist must balance {project.tone} choices against "
            f"the world rules: {canon.world_summary or 'an unstable world order'}."
        ),
        character_summaries=character_summaries,
        chapters=chapters,
    )
    store.outlines[project.id] = outline
    project.status = "outlined"
    project.updated_at = utc_now()
    return outline


def get_outline(project_id: str) -> StoryOutline:
    _get_project(project_id)
    outline = store.outlines.get(project_id)
    if outline is None:
        raise DomainError("outline_not_found", "Outline not found.", status_code=404)
    return outline


def create_chapter(project_id: str, payload: dict[str, str | None]) -> Chapter:
    _get_project(project_id)
    chapter = Chapter(
        project_id=project_id,
        outline_item_id=payload.get("outline_item_id"),
        title=str(payload["title"]),
        summary=str(payload["summary"]),
    )
    store.chapters[chapter.id] = chapter
    store.chapter_versions[chapter.id] = []
    return chapter


def generate_chapter_draft(chapter_id: str, payload: dict[str, str]) -> ChapterVersion:
    chapter = _get_chapter(chapter_id)
    outline = store.outlines.get(chapter.project_id)
    if outline is None:
        raise DomainError(
            "outline_required",
            "Generate the outline before generating a chapter draft.",
            status_code=409,
        )
    canon = store.canons[chapter.project_id]
    content = "\n\n".join(
        [
            f"{chapter.title}",
            f"{payload['chapter_goal']} The scene follows {payload['context_window_strategy']}.",
            (
                f"World context: {canon.world_summary or 'No world summary yet.'} "
                f"Style constraints: {', '.join(canon.style_constraints) or 'none'}."
            ),
            f"Summary seed: {chapter.summary}",
        ]
    )
    version = _create_version(
        chapter_id=chapter.id,
        content=content,
        source_type="draft_generation",
        source_ref_id=chapter.outline_item_id,
        author_type="system",
        version_note="Initial chapter draft",
        activate=True,
    )
    return version


def get_chapter(chapter_id: str) -> dict[str, object]:
    chapter = _get_chapter(chapter_id)
    return {
        "chapter": chapter,
        "content": _current_content(chapter),
        "current_version": (
            _get_version(chapter.current_version_id)
            if chapter.current_version_id is not None
            else None
        ),
    }


def save_chapter(chapter_id: str, content: str) -> ChapterVersion:
    chapter = _get_chapter(chapter_id)
    version = _create_version(
        chapter_id=chapter.id,
        content=content,
        source_type="manual_edit",
        source_ref_id=chapter.current_version_id,
        author_type="user",
        version_note="Manual chapter save",
        activate=True,
    )
    return version


def create_paragraph_edit(chapter_id: str, payload: dict[str, object]) -> ParagraphEditSuggestion:
    chapter = _get_chapter(chapter_id)
    if chapter.current_version_id is None:
        raise DomainError(
            "chapter_content_required",
            "Chapter content is required before editing.",
            status_code=409,
        )
    content = _current_content(chapter)
    operation = str(payload["operation"])
    if operation not in ALLOWED_EDIT_OPERATIONS:
        raise DomainError(
            "invalid_operation",
            "Unsupported edit operation.",
            details={"operation": operation},
            status_code=400,
        )
    start = int(payload["selection_start"])
    end = int(payload["selection_end"])
    selected = _validate_selection(content, start, end)
    candidate = _build_edit_candidate(
        operation=operation,
        selected=selected,
        instruction=str(payload.get("instruction", "")),
    )
    suggestion = ParagraphEditSuggestion(
        chapter_id=chapter.id,
        base_version_id=chapter.current_version_id,
        selection_start=start,
        selection_end=end,
        operation=operation,
        instruction=str(payload.get("instruction", "")),
        candidate_content=candidate,
    )
    store.edit_suggestions[suggestion.id] = suggestion
    return suggestion


def create_qa_scan(chapter_id: str) -> QaScan:
    chapter = _get_chapter(chapter_id)
    if chapter.current_version_id is None:
        raise DomainError(
            "chapter_content_required",
            "Chapter content is required before QA scan.",
            status_code=409,
        )
    content = _current_content(chapter)
    issues = _build_qa_issues(chapter.id, chapter.current_version_id, content)
    scan = QaScan(
        chapter_id=chapter.id,
        base_version_id=chapter.current_version_id,
        status="completed",
        summary=f"Detected {len(issues)} issue(s) for review.",
        issues=issues,
    )
    for issue in issues:
        issue.scan_id = scan.id
    store.scans[scan.id] = scan
    store.chapter_scans.setdefault(chapter.id, []).append(scan.id)
    for issue in issues:
        store.issues[issue.id] = issue
    return scan


def get_qa_scan(chapter_id: str, scan_id: str) -> QaScan:
    _get_chapter(chapter_id)
    scan = store.scans.get(scan_id)
    if scan is None or scan.chapter_id != chapter_id:
        raise DomainError("scan_not_found", "QA scan not found.", status_code=404)
    return scan


def create_issue_fix(issue_id: str, allowed_range: dict[str, int], strategy: str) -> dict[str, object]:
    issue = _get_issue(issue_id)
    chapter = _get_chapter(issue.chapter_id)
    base_version = _get_version(store.scans[issue.scan_id].base_version_id)
    range_start = int(allowed_range["start"])
    range_end = int(allowed_range["end"])
    if range_start > issue.start_offset or range_end < issue.end_offset:
        raise DomainError(
            "range_too_narrow",
            "Allowed range must fully cover the issue excerpt.",
            status_code=400,
        )
    if range_start < 0 or range_end > len(base_version.content) or range_start >= range_end:
        raise DomainError(
            "invalid_fix_range",
            "Allowed fix range is invalid.",
            status_code=400,
        )
    excerpt = base_version.content[range_start:range_end]
    candidate = excerpt + f"\n[Fix applied: {strategy}. Suggestion: {issue.suggested_fix}]"
    version = _create_version(
        chapter_id=chapter.id,
        content=_replace_range(base_version.content, range_start, range_end, candidate),
        source_type="qa_fix",
        source_ref_id=issue.id,
        author_type="system",
        version_note=f"Fix candidate for {issue.issue_type}",
        activate=False,
    )
    return {
        "version": version,
        "affected_range": {"start": range_start, "end": range_end},
    }


def list_versions(chapter_id: str) -> list[ChapterVersion]:
    _get_chapter(chapter_id)
    version_ids = store.chapter_versions.get(chapter_id, [])
    return [_get_version(version_id) for version_id in version_ids]


def create_snapshot(chapter_id: str, note: str) -> ChapterVersion:
    chapter = _get_chapter(chapter_id)
    if chapter.current_version_id is None:
        raise DomainError(
            "chapter_content_required",
            "Chapter content is required before snapshot.",
            status_code=409,
        )
    return _create_version(
        chapter_id=chapter.id,
        content=_current_content(chapter),
        source_type="snapshot",
        source_ref_id=chapter.current_version_id,
        author_type="user",
        version_note=note,
        activate=False,
    )


def get_diff(version_id: str, base_version_id: str) -> dict[str, object]:
    target = _get_version(version_id)
    base = _get_version(base_version_id)
    if target.chapter_id != base.chapter_id:
        raise DomainError(
            "cross_chapter_diff_forbidden",
            "Cannot diff versions from different chapters.",
            status_code=400,
        )
    diff = list(
        difflib.unified_diff(
            base.content.splitlines(),
            target.content.splitlines(),
            fromfile=base.id,
            tofile=target.id,
            lineterm="",
        )
    )
    return {"version_id": target.id, "base_version_id": base.id, "diff": diff}


def restore_version(version_id: str) -> ChapterVersion:
    source = _get_version(version_id)
    chapter = _get_chapter(source.chapter_id)
    restored = _create_version(
        chapter_id=chapter.id,
        content=source.content,
        source_type="restore",
        source_ref_id=source.id,
        author_type="system",
        version_note=f"Restored from {source.id}",
        activate=True,
    )
    return restored


def export_project(project_id: str, export_format: str) -> dict[str, str]:
    project = _get_project(project_id)
    if export_format not in ALLOWED_EXPORT_FORMATS:
        raise DomainError(
            "invalid_export_format",
            "Unsupported export format.",
            details={"format": export_format},
            status_code=400,
        )
    chapters = [
        chapter
        for chapter in store.chapters.values()
        if chapter.project_id == project_id and chapter.current_version_id is not None
    ]
    chapters.sort(key=lambda chapter: chapter.created_at)
    if export_format == "md":
        lines = [f"# {project.title}", "", project.premise]
        for chapter in chapters:
            lines.extend(["", f"## {chapter.title}", "", _current_content(chapter)])
        return {"format": export_format, "content": "\n".join(lines)}
    body = [project.title, project.premise]
    for chapter in chapters:
        body.extend(["", chapter.title, _current_content(chapter)])
    return {"format": export_format, "content": "\n".join(body)}


def _create_version(
    chapter_id: str,
    content: str,
    source_type: str,
    source_ref_id: str | None,
    author_type: str,
    version_note: str,
    activate: bool,
) -> ChapterVersion:
    version = ChapterVersion(
        chapter_id=chapter_id,
        content=content,
        source_type=source_type,
        source_ref_id=source_ref_id,
        author_type=author_type,
        version_note=version_note,
    )
    store.versions[version.id] = version
    store.chapter_versions.setdefault(chapter_id, []).append(version.id)
    chapter = _get_chapter(chapter_id)
    if activate:
        chapter.current_version_id = version.id
        chapter.updated_at = utc_now()
    return version


def _build_edit_candidate(operation: str, selected: str, instruction: str) -> str:
    if operation == "rewrite":
        return f"Rewritten: {selected} ({instruction})".strip()
    if operation == "expand":
        return f"{selected}\nExpanded detail: {instruction or 'add sensory detail'}"
    if operation == "compress":
        return f"Compressed: {selected[: max(20, len(selected) // 2)].strip()}"
    if operation == "tone_shift":
        return f"Tone-adjusted: {selected} [{instruction or 'shift tone'}]"
    return f"Style-adjusted: {selected} [{instruction or 'shift style'}]"


def _build_qa_issues(
    chapter_id: str,
    version_id: str,
    content: str,
) -> list[QaIssue]:
    excerpt = content[: min(len(content), 120)] or "No content"
    issue_map = [
        ("logic_gap", "medium", "Logic jump", "The transition needs an explicit bridge."),
        ("canon_conflict", "high", "Canon conflict", "The scene drifts from the canon."),
        ("plot_discontinuity", "medium", "Plot break", "The plot consequence is underdeveloped."),
        ("redundancy", "low", "Repeated info", "The chapter repeats known information."),
        ("foreshadowing_miss", "medium", "Loose foreshadowing", "A setup item is not paid off."),
        ("voice_drift", "medium", "Voice drift", "Character voice drifts from the canon."),
    ]
    issues: list[QaIssue] = []
    issue_window = max(20, len(excerpt))
    for index, (issue_type, severity, title, description) in enumerate(issue_map):
        start = min(index * 5, max(0, len(content) - 1))
        end = min(len(content), start + issue_window)
        if start == end:
            start = 0
            end = len(content)
        issues.append(
            QaIssue(
                scan_id="pending",
                chapter_id=chapter_id,
                issue_type=issue_type,
                severity=severity,
                title=title,
                description=description,
                evidence_excerpt=content[start:end] or excerpt,
                suggested_fix=f"Clarify and tighten the text for {issue_type}.",
                start_offset=start,
                end_offset=end,
            )
        )
    return issues


def _replace_range(content: str, start: int, end: int, replacement: str) -> str:
    return f"{content[:start]}{replacement}{content[end:]}"


def serialize_entity(entity: object) -> dict[str, object]:
    return asdict(entity)
