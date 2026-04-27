from __future__ import annotations

import difflib
from typing import Iterable

from fastapi import HTTPException

from apps.backend.models import (
    Chapter,
    ChapterDraft,
    ChapterStatus,
    ChapterTask,
    OutlineOption,
    Project,
    ProjectCreate,
    ProjectMemory,
    RewriteRequest,
    RewriteResult,
    TaskCreateRequest,
    TaskMode,
    TaskStatus,
    Template,
    new_id,
    utc_now,
)
from apps.backend.store import InMemoryStore


MAX_CHAPTERS_PER_TASK = 10
MAX_REWRITES = 5
PASS_SCORE = 8.0


class DomainError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def ensure_chapter_limit(chapter_count: int) -> int:
    if chapter_count < 1 or chapter_count > MAX_CHAPTERS_PER_TASK:
        raise DomainError(
            "INVALID_ARGUMENT",
            "chapter_count must be between 1 and 10",
            {"chapter_count": chapter_count},
        )
    return chapter_count


def is_passing_score(score: float) -> bool:
    return score >= PASS_SCORE


def select_highest_scored_option(options: Iterable[OutlineOption]) -> OutlineOption:
    return max(options, key=lambda option: option.final_score)


def select_highest_scored_draft(drafts: Iterable[ChapterDraft]) -> ChapterDraft:
    return max(drafts, key=lambda draft: draft.final_score)


class NovelService:
    def __init__(self, db: InMemoryStore) -> None:
        self.db = db

    def create_project(self, payload: ProjectCreate) -> Project:
        self._assert_content_safe(
            [
                payload.title,
                payload.summary,
                *payload.character_cards,
                *payload.world_rules,
                *payload.event_summary,
            ]
        )
        project = Project(
            id=new_id("project"),
            title=payload.title,
            genre=payload.genre,
            length_type=payload.length_type,
            template_id=payload.template_id,
            mode_default=payload.mode_default,
            summary=payload.summary,
            memory=ProjectMemory(
                global_outline=payload.summary,
                character_cards=payload.character_cards,
                world_rules=payload.world_rules,
                event_summary=payload.event_summary,
            ),
        )
        self.db.projects[project.id] = project
        self.db.log("project_created", {"project_id": project.id})
        return project

    def get_project(self, project_id: str) -> Project:
        project = self.db.projects.get(project_id)
        if not project:
            raise DomainError("INVALID_ARGUMENT", "project not found", {"project_id": project_id})
        return project

    def create_task(self, project_id: str, payload: TaskCreateRequest) -> ChapterTask:
        project = self.get_project(project_id)
        ensure_chapter_limit(payload.chapter_count)
        self._ensure_quota(payload.chapter_count)
        self._ensure_no_running_task(project)
        task = ChapterTask(
            id=new_id("task"),
            project_id=project_id,
            start_chapter_index=payload.start_chapter_index,
            requested_chapter_count=payload.chapter_count,
            mode=payload.mode,
            status=TaskStatus.queued,
            current_chapter_index=payload.start_chapter_index,
        )
        project.tasks.append(task)
        self.db.log("task_created", {"task_id": task.id, "project_id": project_id})
        return task

    def run_task(self, project_id: str, task_id: str) -> ChapterTask:
        project = self.get_project(project_id)
        task = self._get_task(project, task_id)
        task.status = TaskStatus.running
        self.db.log("task_started", {"task_id": task.id})
        start = task.current_chapter_index
        stop = task.start_chapter_index + task.requested_chapter_count
        for chapter_index in range(start, stop):
            chapter = self._generate_chapter(project, chapter_index)
            task.chapter_ids.append(chapter.id)
            task.current_chapter_index = chapter_index
            if task.mode == TaskMode.manual and not chapter.confirmed_by_user:
                task.status = TaskStatus.waiting_user_confirm
                return task
        task.status = TaskStatus.completed
        task.finished_at = utc_now()
        self.db.user_quota.free_remaining = max(
            0, self.db.user_quota.free_remaining - task.requested_chapter_count
        )
        self.db.user_quota.monthly_remaining = max(
            0, self.db.user_quota.monthly_remaining - task.requested_chapter_count
        )
        self.db.log("task_completed", {"task_id": task.id})
        return task

    def confirm_chapter(self, project_id: str, chapter_id: str) -> ChapterTask:
        project = self.get_project(project_id)
        chapter = self._get_chapter(project, chapter_id)
        chapter.confirmed_by_user = True
        chapter.status = ChapterStatus.confirmed
        pending_task = next(
            (task for task in project.tasks if task.status == TaskStatus.waiting_user_confirm),
            None,
        )
        if not pending_task:
            raise DomainError("INVALID_ARGUMENT", "no task waiting for confirmation")
        next_index = chapter.chapter_index + 1
        limit = pending_task.start_chapter_index + pending_task.requested_chapter_count
        if next_index < limit:
            pending_task.current_chapter_index = next_index
            return self.run_task(project.id, pending_task.id)
        pending_task.status = TaskStatus.completed
        pending_task.finished_at = utc_now()
        self.db.log("chapter_confirmed", {"chapter_id": chapter.id})
        return pending_task

    def rewrite_paragraph(self, project_id: str, chapter_id: str, payload: RewriteRequest) -> RewriteResult:
        _ = self.get_project(project_id)
        self._assert_content_safe([payload.paragraph, payload.instruction])
        updated = f"{payload.paragraph}\n[Rewrite] {payload.instruction}"
        return RewriteResult(
            original=payload.paragraph,
            updated=updated,
            diff=self._make_diff(payload.paragraph, updated),
            consistency_note="Review character and world-state continuity after rewrite.",
        )

    def expand_paragraph(self, project_id: str, chapter_id: str, payload: RewriteRequest) -> RewriteResult:
        _ = self.get_project(project_id)
        self._assert_content_safe([payload.paragraph, payload.instruction])
        updated = f"{payload.paragraph}\n[Expanded detail] {payload.instruction}"
        return RewriteResult(
            original=payload.paragraph,
            updated=updated,
            diff=self._make_diff(payload.paragraph, updated),
            consistency_note="Expanded passage may affect pacing and chapter continuity.",
        )

    def create_template(self, template: Template) -> Template:
        self.db.templates[template.id] = template
        self.db.log("template_created", {"template_id": template.id})
        return template

    def list_templates(self) -> list[Template]:
        return list(self.db.templates.values())

    def publish_template(self, template_id: str) -> Template:
        template = self.db.templates[template_id]
        template.status = "published"
        self.db.log("template_published", {"template_id": template_id})
        return template

    def adjust_quota(self, free_delta: int, monthly_delta: int) -> dict[str, int]:
        self.db.user_quota.free_remaining += free_delta
        self.db.user_quota.monthly_remaining += monthly_delta
        self.db.log("quota_adjusted", {"free_delta": free_delta, "monthly_delta": monthly_delta})
        return {
            "free_remaining": self.db.user_quota.free_remaining,
            "monthly_remaining": self.db.user_quota.monthly_remaining,
        }

    def _ensure_quota(self, requested: int) -> None:
        if self.db.user_quota.free_remaining + self.db.user_quota.monthly_remaining < requested:
            raise DomainError("QUOTA_EXCEEDED", "insufficient quota", {"requested": requested})

    def _ensure_no_running_task(self, project: Project) -> None:
        if any(task.status in {TaskStatus.queued, TaskStatus.running, TaskStatus.waiting_user_confirm} for task in project.tasks):
            raise DomainError("TASK_CONFLICT", "project already has an active task")

    def _assert_content_safe(self, values: Iterable[str]) -> None:
        lowered = " ".join(values).lower()
        hit = next((term for term in self.db.safety_policy.blocked_terms if term in lowered), None)
        if hit:
            raise DomainError("CONTENT_BLOCKED", "content blocked by safety policy", {"term": hit})

    def _generate_chapter(self, project: Project, chapter_index: int) -> Chapter:
        chapter = Chapter(
            id=new_id("chapter"),
            chapter_index=chapter_index,
            title=f"Chapter {chapter_index}",
            status=ChapterStatus.outlining,
        )
        chapter.outline_options = self._build_outline_options(project, chapter_index)
        selected = select_highest_scored_option(chapter.outline_options)
        selected.selected = True
        chapter.selected_option_id = selected.id
        chapter.status = ChapterStatus.outline_selected
        drafts = self._build_drafts(project, chapter_index, selected)
        chapter.drafts = drafts
        best = select_highest_scored_draft(drafts)
        best.selected = True
        chapter.final_draft_id = best.id
        chapter.rewrite_count = len(drafts) - 1
        if not is_passing_score(best.final_score):
            chapter.needs_manual_review = True
            chapter.status = ChapterStatus.needs_manual_review
        else:
            chapter.status = ChapterStatus.completed
        project.chapters.append(chapter)
        project.memory.latest_chapter_index = chapter_index
        project.memory.event_summary.append(f"Chapter {chapter_index}: {selected.key_event}")
        project.updated_at = utc_now()
        self.db.log(
            "chapter_generated",
            {
                "project_id": project.id,
                "chapter_id": chapter.id,
                "selected_option_id": selected.id,
                "final_draft_id": best.id,
                "needs_manual_review": chapter.needs_manual_review,
            },
        )
        return chapter

    def _build_outline_options(self, project: Project, chapter_index: int) -> list[OutlineOption]:
        options: list[OutlineOption] = []
        base = [
            ("A hidden clue changes the alliance map", 8.2, 8.0, 8.4),
            ("A public confrontation raises emotional stakes", 8.8, 8.4, 8.7),
            ("A quiet detour deepens lore but slows pacing", 7.8, 8.6, 7.5),
        ]
        for index, (theme, plot, consistency, hook) in enumerate(base, start=1):
            options.append(
                OutlineOption(
                    id=new_id("option"),
                    option_no=index,
                    content=f"Chapter {chapter_index} option {index}: {theme}.",
                    core_conflict=f"Conflict {index} for {project.title}",
                    key_event=f"Key event {index} for chapter {chapter_index}",
                    ending_hook=f"Hook {index} for chapter {chapter_index}",
                    score_plot=plot,
                    score_consistency=consistency,
                    score_hook=hook,
                    final_score=round((plot + consistency + hook) / 3, 2),
                    editor_comment=f"Option {index} balances continuity and momentum.",
                )
            )
        return options

    def _build_drafts(
        self,
        project: Project,
        chapter_index: int,
        option: OutlineOption,
    ) -> list[ChapterDraft]:
        if project.genre == "horror":
            scores = [7.4, 7.6, 7.7, 7.8, 7.85, 7.9]
        else:
            scores = [7.6, 8.4]
        drafts: list[ChapterDraft] = []
        for revision_no, score in enumerate(scores, start=1):
            draft = ChapterDraft(
                id=new_id("draft"),
                revision_no=revision_no,
                content=(
                    f"{project.title} chapter {chapter_index} revision {revision_no}. "
                    f"Built from selected option: {option.content}"
                ),
                score_readability=round(score - 0.1, 2),
                score_tension=round(score, 2),
                score_consistency=round(min(score + 0.1, 8.9), 2),
                final_score=score,
                issue_summary=(
                    "Needs stronger emotional payoff." if score < PASS_SCORE else "Meets release quality threshold."
                ),
            )
            drafts.append(draft)
            if is_passing_score(score):
                break
        return drafts

    def _make_diff(self, original: str, updated: str) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        matcher = difflib.ndiff(original.splitlines(), updated.splitlines())
        for line in matcher:
            prefix = line[:2]
            if prefix == "  ":
                result.append({"type": "unchanged", "text": line[2:]})
            elif prefix == "- ":
                result.append({"type": "removed", "text": line[2:]})
            elif prefix == "+ ":
                result.append({"type": "added", "text": line[2:]})
        return result

    def _get_task(self, project: Project, task_id: str) -> ChapterTask:
        task = next((item for item in project.tasks if item.id == task_id), None)
        if not task:
            raise DomainError("INVALID_ARGUMENT", "task not found", {"task_id": task_id})
        return task

    def _get_chapter(self, project: Project, chapter_id: str) -> Chapter:
        chapter = next((item for item in project.chapters if item.id == chapter_id), None)
        if not chapter:
            raise DomainError("INVALID_ARGUMENT", "chapter not found", {"chapter_id": chapter_id})
        return chapter


def to_http_exception(error: DomainError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": error.code, "message": error.message, "details": error.details})
