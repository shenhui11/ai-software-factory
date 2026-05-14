from __future__ import annotations

import difflib
import threading
from typing import Iterable

from fastapi import HTTPException

from apps.backend.models import (
    Chapter,
    ChapterDraft,
    ChapterStatus,
    ChapterTask,
    FoundationTaskStatus,
    GenreConfig,
    MembershipPlan,
    OutlineOption,
    Order,
    Project,
    ProjectCreate,
    ProjectFoundationTask,
    ProjectMemory,
    ChapterTransformRequest,
    ProjectFoundationRequest,
    RewriteResult,
    TaskCreateRequest,
    TaskMode,
    TaskStatus,
    Template,
    new_id,
    utc_now,
)
from apps.backend.agent_runner import AgentReviewResult, AgentRunner
from apps.backend.store import InMemoryStore


MAX_CHAPTERS_PER_TASK = 10
MAX_REWRITES = 5
PASS_SCORE = 8.0
FAILED_DRAFT_TEXT = "内容生成失败，已返回兜底文本。"
STYLE_ALERT_PENALTY = 0.3
GENRE_ALERT_PENALTY = 0.55
FALLBACK_TEMPLATE_ID = "tpl-system-romance"


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


def ensure_chapter_limit(chapter_count: int) -> int:
    if chapter_count < 1 or chapter_count > MAX_CHAPTERS_PER_TASK:
        raise DomainError(
            "INVALID_ARGUMENT",
            "续写章节数必须在 1 到 10 之间",
            {"chapter_count": chapter_count},
        )
    return chapter_count


def is_passing_score(score: float) -> bool:
    return score >= PASS_SCORE


def select_highest_scored_option(options: Iterable[OutlineOption]) -> OutlineOption:
    return max(options, key=lambda option: (option.final_score, option.score_phase_fit, option.score_hook))


def select_highest_scored_draft(drafts: Iterable[ChapterDraft]) -> ChapterDraft:
    return max(drafts, key=lambda draft: draft.final_score)




class NovelService:
    def __init__(self, db: InMemoryStore, agent_runner: AgentRunner | None = None) -> None:
        self.db = db
        self.agent_runner = agent_runner or AgentRunner()
        self._foundation_task_threads: dict[str, threading.Thread] = {}

    def _set_foundation_task_progress(self, task: ProjectFoundationTask, stage: str, message: str) -> None:
        task.progress_stage = stage
        task.progress_message = message
        self.db.save_foundation_task(task)

    def _set_task_progress(self, project: Project, task: ChapterTask, stage: str, message: str) -> None:
        task.progress_stage = stage
        task.progress_message = message
        project.updated_at = utc_now()
        self.db.save_project(project)

    def _cleanup_stale_tasks(self, project: Project) -> bool:
        _ = project
        return False

    def list_projects(self, user_id: str) -> list[Project]:
        projects = [project for project in self.db.projects.values() if project.user_id == user_id]
        for project in projects:
            self._cleanup_stale_tasks(project)
        return projects

    def list_genres(self) -> list[dict[str, str]]:
        configured = {
            item.value: {"value": item.value, "label": item.label}
            for item in self.db.genre_configs.values()
        }
        for template in self.db.templates.values():
            for genre in template.genres or ([template.genre] if template.genre.strip() else []):
                cleaned = str(genre).strip()
                if cleaned and cleaned not in configured:
                    configured[cleaned] = {"value": cleaned, "label": cleaned}
        for project in self.db.projects.values():
            for genre in project.genres or ([project.genre] if project.genre.strip() else []):
                cleaned = str(genre).strip()
                if cleaned and cleaned not in configured:
                    configured[cleaned] = {"value": cleaned, "label": cleaned}
        return list(configured.values())

    def create_project(self, user_id: str | ProjectCreate, payload: ProjectCreate | None = None) -> Project:
        if payload is None:
            if not isinstance(user_id, ProjectCreate):
                raise TypeError("create_project() missing required payload")
            payload = user_id
            user_id = ""
        if not payload.title.strip():
            raise DomainError("INVALID_ARGUMENT", "项目名称不能为空")
        print(
            (
                f"[project_create] start user_id={user_id} title={payload.title!r} genre={payload.genre!r} "
                f"template_id={payload.template_id!r} summary_len={len(payload.summary)} "
                f"character_cards={len(payload.character_cards)} world_rules={len(payload.world_rules)} "
                f"event_summary={len(payload.event_summary)}"
            ),
            flush=True,
        )
        payload.summary = payload.summary.strip()
        payload.genres = [item.strip() for item in payload.genres if item.strip()]
        if not payload.genres:
            payload.genres = [payload.genre.strip() or "fantasy"]
        payload.genre = payload.genres[0]
        payload.template_id = self._resolve_project_template_id(payload.template_id)
        payload.character_cards = [item.strip() for item in payload.character_cards if item.strip()]
        payload.world_rules = [item.strip() for item in payload.world_rules if item.strip()]
        payload.event_summary = [item.strip() for item in payload.event_summary if item.strip()]
        print(
            (
                f"[project_create] save_form_values=True summary_len={len(str(payload.summary))} "
                f"character_cards={len(payload.character_cards)} world_rules={len(payload.world_rules)} "
                f"event_summary={len(payload.event_summary)}"
            ),
            flush=True,
        )
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
            user_id=user_id,
            title=payload.title,
            genre=payload.genre,
            genres=payload.genres,
            length_type=payload.length_type,
            template_id=payload.template_id,
            mode_default=payload.mode_default,
            summary=payload.summary,
            memory=ProjectMemory(
                global_outline=payload.summary,
                character_cards=payload.character_cards,
                character_profiles=self._seed_character_profiles(payload.character_cards),
                relationship_states=[],
                world_rules=payload.world_rules,
                event_summary=payload.event_summary,
                story_beats=self._normalize_story_beats(payload.story_beats)
                or self._seed_story_beats(
                    payload.title,
                    payload.genre,
                    payload.summary,
                    payload.character_cards,
                    payload.world_rules,
                    payload.event_summary,
                ),
                active_phase={},
                chapter_summaries=[],
                timeline_nodes=self._seed_timeline_nodes(payload.event_summary),
                foreshadow_threads=[],
                major_events=self._seed_major_events(payload.event_summary),
                fact_records=self._seed_fact_records(payload.character_cards, payload.event_summary),
            ),
        )
        self._refresh_story_planning(project)
        template = self.db.templates.get(payload.template_id)
        if template:
            template.usage_count += 1
            self.db.save_template(template)
        self.db.save_project(project)
        self.db.ensure_user_state(user_id)
        self.db.log("project_created", {"project_id": project.id, "user_id": user_id})
        print(f"[project_create] success project_id={project.id} user_id={user_id}", flush=True)
        return project

    def _resolve_project_template_id(self, template_id: str) -> str:
        normalized = template_id.strip()
        if normalized and normalized in self.db.templates:
            return normalized
        if FALLBACK_TEMPLATE_ID in self.db.templates:
            return FALLBACK_TEMPLATE_ID
        available_template = next(iter(self.db.templates.keys()), "")
        return available_template

    def generate_project_foundation(self, payload: ProjectFoundationRequest) -> dict[str, object]:
        if not payload.title.strip():
            raise DomainError("INVALID_ARGUMENT", "项目名称不能为空")
        foundation = self.agent_runner.generate_project_foundation(
            {
                "title": payload.title.strip(),
                "genre": payload.genre.strip() or "fantasy",
                "genres": payload.genres or [payload.genre.strip() or "fantasy"],
                "length_type": payload.length_type.strip() or "long",
                "template_id": payload.template_id or "",
                "summary": payload.summary.strip(),
                "character_cards": [item.strip() for item in payload.character_cards if item.strip()],
                "world_rules": [item.strip() for item in payload.world_rules if item.strip()],
                "event_summary": [item.strip() for item in payload.event_summary if item.strip()],
            }
        )
        defaults = self._default_foundation_bundle(payload.genre.strip() or "fantasy", payload.title.strip())
        user_summary = payload.summary.strip()
        user_character_cards = self._normalized_string_list(payload.character_cards)
        user_world_rules = self._normalized_string_list(payload.world_rules)
        user_event_summary = self._normalized_string_list(payload.event_summary)
        summary = user_summary or str(foundation["summary"]).strip() or str(defaults["summary"])
        character_cards = user_character_cards or self._normalized_string_list(foundation["character_cards"]) or list(defaults["character_cards"])
        world_rules = user_world_rules or self._normalized_string_list(foundation["world_rules"]) or list(defaults["world_rules"])
        event_summary = user_event_summary or self._normalized_string_list(foundation["event_summary"]) or list(defaults["event_summary"])
        story_beats = self._seed_story_beats(
            payload.title.strip(),
            payload.genre.strip() or "fantasy",
            summary,
            character_cards,
            world_rules,
            event_summary,
        )
        merged = {
            "summary": summary,
            "character_cards": character_cards,
            "world_rules": world_rules,
            "event_summary": event_summary,
            "story_beats": story_beats,
            "active_phase": story_beats[0] if story_beats else {},
            "source": foundation.get("source", "local"),
            "fallback": foundation.get("fallback", False),
        }
        self._assert_content_safe(
            [
                payload.title,
                merged["summary"],
                *merged["character_cards"],
                *merged["world_rules"],
                *merged["event_summary"],
            ]
        )
        self.db.log(
            "project_foundation_generated",
            {
                "title": payload.title.strip(),
                "genre": payload.genre.strip() or "fantasy",
                "genres": payload.genres or [payload.genre.strip() or "fantasy"],
                "source": merged["source"],
                "fallback": merged["fallback"],
            },
        )
        return merged

    def create_project_foundation_task(self, user_id: str, payload: ProjectFoundationRequest) -> ProjectFoundationTask:
        if not payload.title.strip():
            raise DomainError("INVALID_ARGUMENT", "项目名称不能为空")
        task = ProjectFoundationTask(
            id=new_id("foundation_task"),
            user_id=user_id,
            status=FoundationTaskStatus.queued,
            progress_stage="queued",
            progress_message="任务已创建，等待开始",
            request=payload,
        )
        self.db.save_foundation_task(task)
        worker = threading.Thread(target=self._run_project_foundation_task, args=(task.id,), daemon=True)
        self._foundation_task_threads[task.id] = worker
        worker.start()
        self.db.log("project_foundation_task_created", {"task_id": task.id, "user_id": user_id})
        return task

    def get_project_foundation_task(self, user_id: str, task_id: str) -> ProjectFoundationTask:
        task = self.db.get_foundation_task(task_id)
        if task is None:
            raise DomainError("INVALID_ARGUMENT", "基础设定任务不存在", {"task_id": task_id})
        if task.user_id != user_id:
            raise DomainError("FORBIDDEN", "无权访问该基础设定任务", {"task_id": task_id}, status_code=403)
        return task

    def _run_project_foundation_task(self, task_id: str) -> None:
        task = self.db.get_foundation_task(task_id)
        if task is None:
            return
        task.status = FoundationTaskStatus.running
        self._set_foundation_task_progress(task, "input_analysis", "正在整理客户输入并准备生成基础设定")
        try:
            self._set_foundation_task_progress(task, "foundation_generation", "正在生成优化后的总纲、角色卡、世界规则和事件摘要")
            result = self.generate_project_foundation(task.request)
            task.result = result
            task.status = FoundationTaskStatus.completed
            task.progress_stage = "completed"
            task.progress_message = "基础设定已生成并可回填表单"
            task.finished_at = utc_now()
            self.db.save_foundation_task(task)
            self.db.log("project_foundation_task_completed", {"task_id": task.id, "user_id": task.user_id})
        except DomainError as exc:
            task.status = FoundationTaskStatus.failed
            task.error_message = exc.message
            task.progress_stage = "failed"
            task.progress_message = exc.message
            task.finished_at = utc_now()
            self.db.save_foundation_task(task)
            self.db.log(
                "project_foundation_task_failed",
                {"task_id": task.id, "user_id": task.user_id, "message": exc.message, "details": exc.details},
            )
        except Exception as exc:
            task.status = FoundationTaskStatus.failed
            task.error_message = str(exc) or "生成项目基础设定失败"
            task.progress_stage = "failed"
            task.progress_message = task.error_message
            task.finished_at = utc_now()
            self.db.save_foundation_task(task)
            self.db.log(
                "project_foundation_task_failed",
                {"task_id": task.id, "user_id": task.user_id, "message": task.error_message},
            )

    def get_project(self, user_id: str | None, project_id: str | None = None) -> Project:
        if project_id is None:
            project_id = str(user_id)
            user_id = None
        project = self.db.projects.get(project_id)
        if not project:
            raise DomainError("INVALID_ARGUMENT", "项目不存在", {"project_id": project_id})
        if user_id is not None and project.user_id != user_id:
            raise DomainError("FORBIDDEN", "无权访问该项目", {"project_id": project_id}, status_code=403)
        if self._reconcile_task_chapter_ids(project):
            self.db.save_project(project)
        self._refresh_story_planning(project)
        self._cleanup_stale_tasks(project)
        return project

    def delete_project(self, user_id: str, project_id: str) -> None:
        project = self.get_project(user_id, project_id)
        print(
            f"[project_delete] user_id={user_id} project_id={project_id} title={project.title!r}",
            flush=True,
        )
        self.db.delete_project(project_id)
        self.db.log("project_deleted", {"project_id": project_id, "user_id": user_id})

    def create_task(
        self,
        user_id: str | TaskCreateRequest,
        project_id: str | None = None,
        payload: TaskCreateRequest | None = None,
    ) -> ChapterTask:
        if payload is None:
            if isinstance(project_id, TaskCreateRequest):
                payload = project_id
                project_id = str(user_id)
                user_id = ""
            elif isinstance(user_id, TaskCreateRequest) and project_id is not None:
                payload = user_id
                user_id = ""
            else:
                raise TypeError("create_task() missing required payload")
        project = self.get_project(user_id, project_id)
        ensure_chapter_limit(payload.chapter_count)
        quota_user_id = user_id if isinstance(user_id, str) and user_id else project.user_id
        self._ensure_quota(quota_user_id, payload.chapter_count)
        self._ensure_no_running_task(project)
        next_chapter_index = max((chapter.chapter_index for chapter in project.chapters), default=0) + 1
        start_chapter_index = max(payload.start_chapter_index, next_chapter_index)
        task = ChapterTask(
            id=new_id("task"),
            project_id=project_id,
            start_chapter_index=start_chapter_index,
            requested_chapter_count=payload.chapter_count,
            mode=payload.mode,
            status=TaskStatus.queued,
            current_chapter_index=start_chapter_index,
            progress_stage="queued",
            progress_message="任务已创建，等待开始",
        )
        project.tasks.append(task)
        self.db.save_project(project)
        self.db.log("task_created", {"task_id": task.id, "project_id": project_id})
        return task

    def run_task(
        self,
        user_id: str | None,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> ChapterTask:
        if task_id is None:
            if project_id is None:
                raise TypeError("run_task() missing required task_id")
            task_id = str(project_id)
            project_id = str(user_id)
            user_id = None
        project = self.get_project(user_id, project_id)
        quota_user_id = user_id if user_id is not None else project.user_id
        task = self._get_task(project, task_id)
        task.status = TaskStatus.running
        self._set_task_progress(project, task, "task_starting", "正在启动章节生成任务")
        self.db.log("task_started", {"task_id": task.id})
        start = task.current_chapter_index
        stop = task.start_chapter_index + task.requested_chapter_count
        for chapter_index in range(start, stop):
            chapter = next((item for item in project.chapters if item.chapter_index == chapter_index), None)
            if chapter is None:
                try:
                    self._consume_quota(quota_user_id, 1)
                except DomainError:
                    task.status = TaskStatus.failed
                    self._set_task_progress(project, task, "failed", "额度不足，任务执行失败")
                    raise
                self._set_task_progress(project, task, "chapter_preparing", f"正在准备第 {chapter_index} 章")
                chapter = self._generate_chapter(project, task, chapter_index)
            if chapter.id not in task.chapter_ids:
                task.chapter_ids.append(chapter.id)
            task.current_chapter_index = chapter_index + 1
            self._set_task_progress(project, task, "chapter_completed", f"第 {chapter_index} 章已完成")
            if task.mode == TaskMode.manual and not chapter.confirmed_by_user:
                task.status = TaskStatus.waiting_user_confirm
                self._set_task_progress(project, task, "waiting_user_confirm", f"第 {chapter_index} 章已生成，等待人工确认")
                return task
        task.status = TaskStatus.completed
        task.progress_stage = "completed"
        task.progress_message = "任务已完成"
        task.finished_at = utc_now()
        self.db.save_project(project)
        self.db.log("task_completed", {"task_id": task.id})
        return task

    def confirm_chapter(self, user_id: str, project_id: str, chapter_id: str) -> ChapterTask:
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        chapter.confirmed_by_user = True
        chapter.status = ChapterStatus.confirmed
        pending_task = next(
            (
                task
                for task in project.tasks
                if task.mode == TaskMode.manual and chapter_id in task.chapter_ids and task.status in {TaskStatus.running, TaskStatus.waiting_user_confirm}
            ),
            None,
        )
        if not pending_task:
            raise DomainError("INVALID_ARGUMENT", "当前没有等待确认的任务")
        pending_task.status = TaskStatus.running
        next_index = chapter.chapter_index + 1
        limit = pending_task.start_chapter_index + pending_task.requested_chapter_count
        self.db.log(
            "chapter_confirmed",
            {
                "chapter_id": chapter.id,
                "task_id": pending_task.id,
                "confirmed_chapter_index": chapter.chapter_index,
                "next_chapter_index": next_index,
                "limit_exclusive": limit,
            },
        )
        if next_index < limit:
            pending_task.current_chapter_index = next_index
            self.db.save_project(project)
            return self.run_task(user_id, project.id, pending_task.id)
        pending_task.status = TaskStatus.completed
        pending_task.finished_at = utc_now()
        self.db.save_project(project)
        return pending_task

    def _reconcile_task_chapter_ids(self, project: Project) -> bool:
        changed = False
        chapters_by_index = {
            chapter.chapter_index: chapter
            for chapter in sorted(project.chapters, key=lambda item: item.chapter_index)
        }
        for task in project.tasks:
            end_exclusive = min(
                task.current_chapter_index,
                task.start_chapter_index + task.requested_chapter_count,
            )
            derived_ids = [
                chapter.id
                for index, chapter in chapters_by_index.items()
                if task.start_chapter_index <= index < end_exclusive
            ]
            if derived_ids != task.chapter_ids:
                task.chapter_ids = derived_ids
                changed = True
        return changed

    def regenerate_chapter_outlines(self, user_id: str, project_id: str, chapter_id: str, user_idea: str = "") -> Chapter:
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        print(
            (
                f"[service] regenerate_chapter_outlines start project_id={project_id} chapter_id={chapter_id} "
                f"user_idea={user_idea.strip()!r}"
            ),
            flush=True,
        )
        self._assert_chapter_editable(chapter)
        chapter.outline_options = self._build_outline_options(project, chapter.chapter_index, user_idea)
        selected = select_highest_scored_option(chapter.outline_options)
        self._select_outline_option(chapter, selected.id)
        self._refresh_chapter_drafts(project, chapter, selected)
        self.db.save_project(project)
        self.db.log(
            "chapter_outlines_regenerated",
            {"project_id": project_id, "chapter_id": chapter_id, "user_idea": user_idea.strip()},
        )
        return chapter

    def select_outline_option(
        self,
        user_id: str | None,
        project_id: str | None = None,
        chapter_id: str | None = None,
        option_id: str | None = None,
    ) -> Chapter:
        if option_id is None:
            if chapter_id is None:
                raise TypeError("select_outline_option() missing required option_id")
            option_id = str(chapter_id)
            chapter_id = str(project_id)
            project_id = str(user_id)
            user_id = None
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        print(f"[service] select_outline_option start project_id={project_id} chapter_id={chapter_id} option_id={option_id}", flush=True)
        self._assert_chapter_editable(chapter)
        selected = self._get_outline_option(chapter, option_id)
        self._select_outline_option(chapter, option_id)
        self._refresh_chapter_drafts(project, chapter, selected)
        self.db.save_project(project)
        self.db.log(
            "chapter_outline_selected",
            {"project_id": project_id, "chapter_id": chapter_id, "option_id": option_id},
        )
        return chapter

    def update_outline_option(
        self,
        user_id: str,
        project_id: str,
        chapter_id: str,
        option_id: str,
        content: str,
        core_conflict: str,
        key_event: str,
        ending_hook: str,
    ) -> Chapter:
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        self._assert_chapter_editable(chapter)
        self._assert_content_safe([content, core_conflict, key_event, ending_hook])
        option = self._get_outline_option(chapter, option_id)
        option.content = content.strip()
        option.core_conflict = core_conflict.strip()
        option.key_event = key_event.strip()
        option.ending_hook = ending_hook.strip()
        option.editor_comment = "该走向已人工修改，并已基于修改内容重新生成正文。"
        self._select_outline_option(chapter, option_id)
        self._refresh_chapter_drafts(project, chapter, option)
        self.db.save_project(project)
        self.db.log(
            "chapter_outline_updated",
            {"project_id": project_id, "chapter_id": chapter_id, "option_id": option_id},
        )
        return chapter

    def regenerate_chapter_draft(self, user_id: str, project_id: str, chapter_id: str) -> Chapter:
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        print(f"[service] regenerate_chapter_draft start project_id={project_id} chapter_id={chapter_id}", flush=True)
        self._assert_chapter_editable(chapter)
        option = self._selected_outline_option(chapter)
        self._refresh_chapter_drafts(project, chapter, option)
        self.db.save_project(project)
        self.db.log("chapter_draft_regenerated", {"project_id": project_id, "chapter_id": chapter_id})
        return chapter

    def update_chapter_draft(
        self,
        user_id: str | None,
        project_id: str | None = None,
        chapter_id: str | None = None,
        content: str | None = None,
    ) -> Chapter:
        if content is None:
            if chapter_id is None:
                raise TypeError("update_chapter_draft() missing required content")
            content = str(chapter_id)
            chapter_id = str(project_id)
            project_id = str(user_id)
            user_id = None
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        self._assert_chapter_editable(chapter)
        cleaned = content.strip()
        if not cleaned:
            raise DomainError("INVALID_ARGUMENT", "章节正文不能为空")
        self._assert_content_safe([cleaned])
        option = self._selected_outline_option(chapter)
        revision_no = max((draft.revision_no for draft in chapter.drafts), default=0) + 1
        context_packet = self._build_context_packet(
            project,
            chapter.chapter_index,
            self._build_draft_query(option, [cleaned[:120]]),
            action="chapter_review",
        )
        if hasattr(self.agent_runner, "review_draft_with_context"):
            review_result = self.agent_runner.review_draft_with_context(
                project,
                chapter,
                option,
                cleaned,
                revision_no,
                context_packet,
            )
        else:
            review_result = self.agent_runner.review_draft(project, chapter, option, cleaned, revision_no)
        if review_result.fallback:
            review_result = AgentReviewResult(
                score_readability=2.4,
                score_tension=2.2,
                score_consistency=2.6,
                final_score=2.4,
                issue_summary="人工修改后的正文评分阶段返回了兜底结果，当前评分无效，需人工复核。",
                source=review_result.source,
                fallback=True,
            )
        consistency_alerts = self._run_consistency_checks(project, chapter, cleaned)
        style_alerts = self._run_style_checks(cleaned)
        genre_alerts = self._run_genre_checks(project, option, cleaned)
        conflict_alerts = self._build_conflict_alerts(project, cleaned)
        draft = ChapterDraft(
            id=new_id("draft"),
            revision_no=revision_no,
            content=cleaned,
            score_readability=review_result.score_readability,
            score_tension=review_result.score_tension,
            score_consistency=review_result.score_consistency,
            final_score=max(
                0.0,
                review_result.final_score
                - 0.4 * len(consistency_alerts)
                - STYLE_ALERT_PENALTY * len(style_alerts)
                - GENRE_ALERT_PENALTY * len(genre_alerts),
            ),
            issue_summary=self._merge_issue_summary(review_result.issue_summary, consistency_alerts, style_alerts, genre_alerts),
            conflict_alerts=conflict_alerts,
            selected=True,
        )
        for item in chapter.drafts:
            item.selected = False
        chapter.drafts.append(draft)
        chapter.final_draft_id = draft.id
        chapter.rewrite_count = max(0, len(chapter.drafts) - 1)
        chapter.needs_manual_review = not is_passing_score(draft.final_score)
        chapter.status = (
            ChapterStatus.needs_manual_review if chapter.needs_manual_review else ChapterStatus.completed
        )
        self._sync_project_memory_for_chapter(project, chapter, option, cleaned)
        self.db.save_project(project)
        self.db.log(
            "chapter_draft_updated",
            {"project_id": project_id, "chapter_id": chapter_id, "revision_no": revision_no},
        )
        self.db.log(
            "agent_called",
            {
                "project_id": project.id,
                "chapter_index": chapter.chapter_index,
                "action": "chapter_review",
                "source": review_result.source,
                "fallback": review_result.fallback,
                "revision_no": revision_no,
            },
        )
        return chapter

    def update_chapter_title(
        self,
        user_id: str | None,
        project_id: str | None = None,
        chapter_id: str | None = None,
        title: str | None = None,
    ) -> Chapter:
        if title is None:
            if chapter_id is None:
                raise TypeError("update_chapter_title() missing required title")
            title = str(chapter_id)
            chapter_id = str(project_id)
            project_id = str(user_id)
            user_id = None
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        self._assert_chapter_editable(chapter)
        cleaned = title.strip()
        if not cleaned:
            raise DomainError("INVALID_ARGUMENT", "章节名称不能为空")
        self._assert_content_safe([cleaned])
        chapter.title = cleaned
        project.updated_at = utc_now()
        self.db.save_project(project)
        self.db.log(
            "chapter_title_updated",
            {"project_id": project_id, "chapter_id": chapter_id, "title": cleaned},
        )
        return chapter

    def delete_chapter(self, user_id: str, project_id: str, chapter_id: str) -> Project:
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        self._assert_chapter_editable(chapter)
        project.chapters = [item for item in project.chapters if item.id != chapter_id]
        self._remove_chapter_from_memory(project, chapter.chapter_index)
        for task in project.tasks:
            if chapter_id in task.chapter_ids:
                task.chapter_ids = [item for item in task.chapter_ids if item != chapter_id]
                if task.current_chapter_index >= chapter.chapter_index:
                    task.current_chapter_index = max(task.start_chapter_index, chapter.chapter_index)
                if task.status in {TaskStatus.queued, TaskStatus.running, TaskStatus.waiting_user_confirm}:
                    task.status = TaskStatus.failed
                    task.finished_at = utc_now()
        print(
            (
                f"[chapter_delete] project_id={project_id} chapter_id={chapter_id} chapter_index={chapter.chapter_index} "
                f"remaining_tasks={[{'id': task.id, 'status': task.status.value, 'chapter_ids': list(task.chapter_ids)} for task in project.tasks]}"
            ),
            flush=True,
        )
        project.updated_at = utc_now()
        self.db.save_project(project)
        self.db.log(
            "chapter_deleted",
            {"project_id": project_id, "chapter_id": chapter_id, "chapter_index": chapter.chapter_index},
        )
        return project

    def clear_active_task(self, user_id: str, project_id: str) -> Project:
        project = self.get_project(user_id, project_id)
        active_task = next(
            (task for task in project.tasks if task.status in {TaskStatus.queued, TaskStatus.running, TaskStatus.waiting_user_confirm}),
            None,
        )
        if not active_task:
            raise DomainError("INVALID_ARGUMENT", "当前项目没有可清理的进行中任务")
        active_chapter_ids = set(active_task.chapter_ids)
        project.tasks = [task for task in project.tasks if task.id != active_task.id]
        if active_chapter_ids:
            removed_indexes = [chapter.chapter_index for chapter in project.chapters if chapter.id in active_chapter_ids]
            project.chapters = [chapter for chapter in project.chapters if chapter.id not in active_chapter_ids]
            for chapter_index in removed_indexes:
                self._remove_chapter_from_memory(project, chapter_index)
        project.updated_at = utc_now()
        self.db.save_project(project)
        self.db.log(
            "active_task_cleared",
            {
                "project_id": project_id,
                "task_id": active_task.id,
                "removed_chapter_count": len(active_chapter_ids),
            },
        )
        return project

    def rewrite_chapter(
        self,
        user_id: str | None,
        project_id: str | None = None,
        chapter_id: str | None = None,
        payload: ChapterTransformRequest | None = None,
    ) -> RewriteResult:
        if payload is None:
            if chapter_id is None:
                raise TypeError("rewrite_chapter() missing required payload")
            payload = chapter_id
            chapter_id = str(project_id)
            project_id = str(user_id)
            user_id = None
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        chapter_content = payload.chapter_content or self._selected_draft_content(chapter)
        target_paragraph = (payload.paragraph or "").strip()
        payload.chapter_content = target_paragraph or chapter_content
        safety_inputs = [payload.instruction, chapter_content]
        if target_paragraph:
            safety_inputs.append(target_paragraph)
        self._assert_content_safe(safety_inputs)
        agent_result = self.agent_runner.rewrite_chapter(project, chapter, payload)
        updated = (
            self._replace_first_match(chapter_content, target_paragraph, agent_result.text)
            if target_paragraph
            else agent_result.text
        )
        self.db.log(
            "agent_called",
            {
                "project_id": project_id,
                "chapter_id": chapter_id,
                "action": "chapter_rewrite",
                "source": agent_result.source,
            },
        )
        return RewriteResult(
            original=chapter_content,
            updated=updated,
            diff=self._make_diff(chapter_content, updated),
            consistency_note="已按目标段落重写，请复核角色设定、世界状态、节奏与上下文连贯性。",
            chapter_updated=updated,
        )

    def remove_chapter_paragraph(
        self,
        user_id: str | None,
        project_id: str | None = None,
        chapter_id: str | None = None,
        payload: ChapterTransformRequest | None = None,
    ) -> RewriteResult:
        if payload is None:
            if chapter_id is None:
                raise TypeError("remove_chapter_paragraph() missing required payload")
            payload = chapter_id
            chapter_id = str(project_id)
            project_id = str(user_id)
            user_id = None
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        chapter_content = payload.chapter_content or self._selected_draft_content(chapter)
        target_paragraph = (payload.paragraph or "").strip()
        if not target_paragraph:
            raise DomainError("INVALID_ARGUMENT", "去除段落时必须提供目标段落")
        self._assert_content_safe([payload.instruction, chapter_content, target_paragraph])
        updated = self._remove_first_match(chapter_content, target_paragraph)
        self.db.log(
            "agent_called",
            {
                "project_id": project_id,
                "chapter_id": chapter_id,
                "action": "chapter_remove",
                "source": "rule",
            },
        )
        return RewriteResult(
            original=chapter_content,
            updated=updated,
            diff=self._make_diff(chapter_content, updated),
            consistency_note="已去除目标段落，请复核事件衔接、角色动机和前后文连贯性。",
            chapter_updated=updated,
        )

    def expand_chapter(
        self,
        user_id: str | None,
        project_id: str | None = None,
        chapter_id: str | None = None,
        payload: ChapterTransformRequest | None = None,
    ) -> RewriteResult:
        if payload is None:
            if chapter_id is None:
                raise TypeError("expand_chapter() missing required payload")
            payload = chapter_id
            chapter_id = str(project_id)
            project_id = str(user_id)
            user_id = None
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        chapter_content = payload.chapter_content or self._selected_draft_content(chapter)
        target_paragraph = (payload.paragraph or "").strip()
        payload.chapter_content = target_paragraph or chapter_content
        safety_inputs = [payload.instruction, chapter_content]
        if target_paragraph:
            safety_inputs.append(target_paragraph)
        self._assert_content_safe(safety_inputs)
        agent_result = self.agent_runner.expand_chapter(project, chapter, payload)
        updated = (
            self._replace_first_match(chapter_content, target_paragraph, agent_result.text)
            if target_paragraph
            else agent_result.text
        )
        self.db.log(
            "agent_called",
            {
                "project_id": project_id,
                "chapter_id": chapter_id,
                "action": "chapter_expand",
                "source": agent_result.source,
            },
        )
        return RewriteResult(
            original=chapter_content,
            updated=updated,
            diff=self._make_diff(chapter_content, updated),
            consistency_note="已按目标段落拓写，请复核扩写节奏、事件推进与上下文连贯性。",
            chapter_updated=updated,
        )

    def create_template(self, user_id: str | Template, template: Template | None = None, username: str | None = None) -> Template:
        if template is None:
            if not isinstance(user_id, Template):
                raise TypeError("create_template() missing required template")
            template = user_id
            user_id = template.owner_user_id or ""
        template.owner_user_id = user_id if template.owner_type == "user" else template.owner_user_id
        template.owner_username = username if template.owner_type == "user" and username else template.owner_username
        self.db.save_template(template)
        self.db.log("template_created", {"template_id": template.id, "user_id": user_id})
        return template

    def update_template(self, user_id: str, template_id: str, payload: dict[str, object], username: str | None = None) -> Template:
        template = self.db.templates.get(template_id)
        if not template:
            raise DomainError("INVALID_ARGUMENT", "模板不存在", {"template_id": template_id})
        owner_matches = template.owner_user_id == user_id or (username and template.owner_username == username)
        if template.owner_type == "user" and not owner_matches:
            raise DomainError("FORBIDDEN", "无权修改该模板", {"template_id": template_id}, status_code=403)
        if template.owner_type == "user":
            template.owner_user_id = user_id
            if username:
                template.owner_username = username
        for field in [
            "name",
            "genre",
            "style_rules",
            "world_template",
            "character_template",
            "outline_template",
            "status",
        ]:
            if field in payload and isinstance(payload[field], str) and payload[field].strip():
                setattr(template, field, payload[field].strip())
        if "genres" in payload and isinstance(payload["genres"], list):
            normalized_genres = [str(item).strip() for item in payload["genres"] if str(item).strip()]
            if normalized_genres:
                template.genres = normalized_genres
                template.genre = normalized_genres[0]
        elif template.genre.strip() and not template.genres:
            template.genres = [template.genre.strip()]
        if "tags" in payload:
            raw_tags = payload["tags"]
            if isinstance(raw_tags, list):
                template.tags = [str(item).strip() for item in raw_tags if str(item).strip()]
        self.db.save_template(template)
        self.db.log("template_updated", {"template_id": template_id})
        return template

    def list_templates(self, user_id: str, username: str | None = None) -> list[Template]:
        return [
            template
            for template in self.db.templates.values()
            if template.owner_type == "system"
            or template.owner_user_id == user_id
            or (username and template.owner_username == username)
        ]

    def publish_template(self, template_id: str) -> Template:
        template = self.db.templates[template_id]
        template.status = "published"
        self.db.save_template(template)
        self.db.log("template_published", {"template_id": template_id})
        return template

    def list_genre_configs(self) -> list[GenreConfig]:
        return sorted(self.db.genre_configs.values(), key=lambda item: item.value)

    def upsert_genre_config(
        self,
        value: str,
        label: str,
        required_any: list[str],
        forbidden_any: list[str],
    ) -> GenreConfig:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise DomainError("INVALID_ARGUMENT", "题材标识不能为空")
        config = GenreConfig(
            value=cleaned_value,
            label=label.strip() or cleaned_value,
            required_any=[item.strip() for item in required_any if item.strip()],
            forbidden_any=[item.strip() for item in forbidden_any if item.strip()],
        )
        self.db.save_genre_config(config)
        self.db.log("genre_config_upserted", {"value": cleaned_value})
        return config

    def adjust_quota(
        self,
        daily_delta: int,
        monthly_delta: int,
        bonus_delta: int,
        user_id: str | None = None,
    ) -> dict[str, int]:
        if user_id:
            quota = self.db.refresh_quota_periods(user_id)
            print(
                (
                    f"[quota_adjust] target_user_id={user_id} "
                    f"before={{'daily_remaining': {quota.daily_remaining}, 'monthly_remaining': {quota.monthly_remaining}, 'bonus_remaining': {quota.bonus_remaining}}} "
                    f"delta={{'daily_delta': {daily_delta}, 'monthly_delta': {monthly_delta}, 'bonus_delta': {bonus_delta}}}"
                ),
                flush=True,
            )
            quota.daily_remaining += daily_delta
            quota.monthly_remaining += monthly_delta
            quota.bonus_remaining += bonus_delta
            self.db.save_user_quota(user_id)
        else:
            quota = self.db.refresh_quota_periods()
            print(
                (
                    f"[quota_adjust] target_user_id=default "
                    f"before={{'daily_remaining': {quota.daily_remaining}, 'monthly_remaining': {quota.monthly_remaining}, 'bonus_remaining': {quota.bonus_remaining}}} "
                    f"delta={{'daily_delta': {daily_delta}, 'monthly_delta': {monthly_delta}, 'bonus_delta': {bonus_delta}}}"
                ),
                flush=True,
            )
            quota.daily_remaining += daily_delta
            quota.monthly_remaining += monthly_delta
            quota.bonus_remaining += bonus_delta
            self.db.save_quota()
        print(
            (
                f"[quota_adjust] target_user_id={user_id or 'default'} "
                f"after={{'daily_remaining': {quota.daily_remaining}, 'monthly_remaining': {quota.monthly_remaining}, 'bonus_remaining': {quota.bonus_remaining}}}"
            ),
            flush=True,
        )
        self.db.log(
            "quota_adjusted",
            {"daily_delta": daily_delta, "monthly_delta": monthly_delta, "bonus_delta": bonus_delta},
        )
        return {
            "daily_remaining": quota.daily_remaining,
            "monthly_remaining": quota.monthly_remaining,
            "bonus_remaining": quota.bonus_remaining,
        }

    def list_membership_plans(self, user_id: str | None = None) -> dict[str, object]:
        if user_id:
            quota = self.db.refresh_quota_periods(user_id)
            active_plan_id = self.db.get_user_active_plan_id(user_id)
        else:
            quota = self.db.refresh_quota_periods()
            active_plan_id = self.db.active_plan_id
        default_plan = self.db.membership_plans[self.db.active_plan_id]
        return {
            "plans": list(self.db.membership_plans.values()),
            "quota": quota,
            "default_plan_id": self.db.active_plan_id,
            "default_plan": default_plan,
            "user_plan_id": active_plan_id,
            "user_plan": self.db.membership_plans[active_plan_id],
            "target_user_id": user_id,
        }

    def create_membership_plan(
        self,
        name: str,
        daily_free_chapters: int,
        monthly_free_chapters: int,
        description: str = "",
    ) -> MembershipPlan:
        plan = MembershipPlan(
            id=new_id("plan"),
            name=name.strip(),
            daily_free_chapters=daily_free_chapters,
            monthly_free_chapters=monthly_free_chapters,
            description=description.strip(),
        )
        self.db.save_membership_plan(plan)
        self.db.log("membership_plan_created", {"plan_id": plan.id})
        return plan

    def update_membership_plan(self, plan_id: str, payload: dict[str, object]) -> MembershipPlan:
        plan = self.db.membership_plans.get(plan_id)
        if not plan:
            raise DomainError("INVALID_ARGUMENT", "套餐不存在", {"plan_id": plan_id})
        if isinstance(payload.get("name"), str) and payload["name"].strip():
            plan.name = str(payload["name"]).strip()
        if isinstance(payload.get("description"), str):
            plan.description = str(payload["description"]).strip()
        if isinstance(payload.get("daily_free_chapters"), int) and int(payload["daily_free_chapters"]) >= 0:
            plan.daily_free_chapters = int(payload["daily_free_chapters"])
        if isinstance(payload.get("monthly_free_chapters"), int) and int(payload["monthly_free_chapters"]) >= 0:
            plan.monthly_free_chapters = int(payload["monthly_free_chapters"])
        self.db.save_membership_plan(plan)
        self.db.log("membership_plan_updated", {"plan_id": plan_id})
        return plan

    def activate_membership_plan(self, plan_id: str, user_id: str | None = None) -> MembershipPlan:
        plan = self.db.membership_plans.get(plan_id)
        if not plan:
            raise DomainError("INVALID_ARGUMENT", "套餐不存在", {"plan_id": plan_id})
        if user_id:
            self.db.user_active_plan_ids[user_id] = plan_id
            self.db.save_user_active_plan(user_id)
        else:
            self.db.active_plan_id = plan_id
            self.db.save_active_plan()
        self.db.log("membership_plan_activated", {"plan_id": plan_id, "target_user_id": user_id})
        return plan

    def list_orders(self) -> list[Order]:
        return list(self.db.orders.values())

    def create_order(self, plan_id: str, amount: float, status: str, note: str = "") -> Order:
        if plan_id not in self.db.membership_plans:
            raise DomainError("INVALID_ARGUMENT", "套餐不存在", {"plan_id": plan_id})
        order = Order(
            id=new_id("order"),
            plan_id=plan_id,
            amount=amount,
            status=status.strip(),
            note=note.strip(),
        )
        self.db.save_order(order)
        self.db.log("order_created", {"order_id": order.id, "plan_id": plan_id, "status": order.status})
        return order

    def update_order(self, order_id: str, payload: dict[str, object]) -> Order:
        order = self.db.orders.get(order_id)
        if not order:
            raise DomainError("INVALID_ARGUMENT", "订单不存在", {"order_id": order_id})
        if isinstance(payload.get("plan_id"), str) and payload["plan_id"] in self.db.membership_plans:
            order.plan_id = str(payload["plan_id"])
        if isinstance(payload.get("amount"), (int, float)) and float(payload["amount"]) >= 0:
            order.amount = float(payload["amount"])
        if isinstance(payload.get("status"), str) and payload["status"].strip():
            order.status = str(payload["status"]).strip()
        if isinstance(payload.get("note"), str):
            order.note = str(payload["note"]).strip()
        self.db.save_order(order)
        self.db.log("order_updated", {"order_id": order_id, "status": order.status})
        return order

    def _ensure_quota(self, user_id: str, requested: int) -> None:
        quota = self.db.refresh_quota_periods(user_id)
        if quota.daily_remaining + quota.monthly_remaining + quota.bonus_remaining < requested:
            raise DomainError("QUOTA_EXCEEDED", "可用额度不足", {"requested": requested})

    def _consume_quota(self, user_id: str, requested: int) -> None:
        self._ensure_quota(user_id, requested)
        quota = self.db.refresh_quota_periods(user_id)
        remaining = requested
        daily_used = min(quota.daily_remaining, remaining)
        quota.daily_remaining -= daily_used
        remaining -= daily_used
        if remaining > 0:
            monthly_used = min(quota.monthly_remaining, remaining)
            quota.monthly_remaining -= monthly_used
            remaining -= monthly_used
        if remaining > 0:
            quota.bonus_remaining -= remaining
        self.db.save_user_quota(user_id)

    def _ensure_no_running_task(self, project: Project) -> None:
        if any(task.status in {TaskStatus.queued, TaskStatus.running, TaskStatus.waiting_user_confirm} for task in project.tasks):
            raise DomainError("TASK_CONFLICT", "当前项目已有进行中的任务")

    def _assert_content_safe(self, values: Iterable[str]) -> None:
        lowered = " ".join(values).lower()
        hit = next((term for term in self.db.safety_policy.blocked_terms if term in lowered), None)
        if hit:
            print(f"[content_blocked] term={hit!r}", flush=True)
            raise DomainError("CONTENT_BLOCKED", "内容触发安全策略，已被拦截", {"term": hit})

    def _generate_chapter(self, project: Project, task: ChapterTask | None, chapter_index: int) -> Chapter:
        chapter = Chapter(
            id=new_id("chapter"),
            chapter_index=chapter_index,
            title=f"第 {chapter_index} 章",
            status=ChapterStatus.outlining,
        )
        project.chapters.append(chapter)
        project.updated_at = utc_now()
        self.db.save_project(project)
        if task is not None:
            self._set_task_progress(project, task, "outline_generation", f"第 {chapter_index} 章：正在生成章节走向")
        chapter.outline_options = self._build_outline_options(project, chapter_index)
        selected = select_highest_scored_option(chapter.outline_options)
        selected.selected = True
        chapter.selected_option_id = selected.id
        chapter.status = ChapterStatus.outline_selected
        drafts = self._build_drafts(project, task, chapter_index, selected)
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
        if task is not None:
            self._set_task_progress(project, task, "memory_sync", f"第 {chapter_index} 章：正在回写章节记忆与结构化信息")
        self._sync_project_memory_for_chapter(project, chapter, selected, best.content)
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

    def _build_outline_options(self, project: Project, chapter_index: int, user_idea: str = "") -> list[OutlineOption]:
        query_text = self._build_outline_query(project, chapter_index, user_idea)
        context_packet = self._build_context_packet(project, chapter_index, query_text, action="chapter_outlines")
        if user_idea.strip():
            context_packet["user_idea"] = user_idea.strip()
        if hasattr(self.agent_runner, "generate_outline_options_with_context"):
            result = self.agent_runner.generate_outline_options_with_context(project, chapter_index, context_packet)
        else:
            result = self.agent_runner.generate_outline_options(project, chapter_index)
        self.db.log(
            "agent_called",
            {
                "project_id": project.id,
                "chapter_index": chapter_index,
                "action": "chapter_outlines",
                "context_packet": context_packet,
                "user_idea": user_idea.strip(),
                "source": result.source,
                "fallback": result.fallback,
            },
        )
        raw_option_preview = []
        for item in result.options[:3]:
            if isinstance(item, dict):
                raw_option_preview.append(
                    {
                        "option_no": item.get("option_no"),
                        "content": str(item.get("content", ""))[:120],
                    }
                )
        print(
            (
                f"[outline_generation] chapter_index={chapter_index} source={result.source} fallback={result.fallback} "
                f"user_idea={user_idea.strip()!r} preview={raw_option_preview}"
            ),
            flush=True,
        )
        options: list[OutlineOption] = []
        for item in result.options:
            score_phase_fit, phase_fit_hits = self._score_outline_phase_fit(project.memory.active_phase, item)
            genre_fit_score, genre_alerts = self._score_outline_multi_genre_fit(project.genres or [project.genre], item)
            original_final_score = float(item["final_score"])
            final_score = round(
                original_final_score * 0.6 + score_phase_fit * 0.2 + genre_fit_score * 0.2,
                2,
            )
            editor_comment = str(item["editor_comment"]).strip()
            if phase_fit_hits:
                editor_comment = f"{editor_comment} 阶段贴合关键词：{' / '.join(phase_fit_hits[:4])}。".strip()
            if genre_alerts:
                editor_comment = f"{editor_comment} 题材提醒：{'；'.join(genre_alerts[:2])}。".strip()
            options.append(
                OutlineOption(
                    id=new_id("option"),
                    option_no=int(item["option_no"]),
                    content=str(item["content"]),
                    core_conflict=str(item["core_conflict"]),
                    key_event=str(item["key_event"]),
                    ending_hook=str(item["ending_hook"]),
                    score_plot=float(item["score_plot"]),
                    score_consistency=float(item["score_consistency"]),
                    score_hook=float(item["score_hook"]),
                    score_phase_fit=score_phase_fit,
                    phase_fit_hits=phase_fit_hits,
                    final_score=final_score,
                    editor_comment=editor_comment,
                )
            )
        return options

    def _score_outline_phase_fit(self, active_phase: dict[str, object], option: dict[str, object]) -> tuple[float, list[str]]:
        if not active_phase:
            return 0.0, []
        phase_terms = self._extract_phase_signal_terms(
            [
                str(active_phase.get("phase_goal", "")),
                *[str(item) for item in active_phase.get("phase_pressure", [])],
                *[str(item) for item in active_phase.get("required_change", [])],
                *[str(item) for item in active_phase.get("foreshadow_to_surface", [])],
            ]
        )
        option_text = "\n".join(
            [
                str(option.get("content", "")),
                str(option.get("core_conflict", "")),
                str(option.get("key_event", "")),
                str(option.get("ending_hook", "")),
            ]
        )
        hits = [term for term in phase_terms if term in option_text][:4]
        if len(hits) >= 4:
            return 9.4, hits
        if len(hits) == 3:
            return 8.8, hits
        if len(hits) == 2:
            return 8.1, hits
        if len(hits) == 1:
            return 7.2, hits
        return 6.2, []

    def _score_outline_genre_fit(self, genre: str, option: dict[str, object]) -> tuple[float, list[str]]:
        option_text = "\n".join(
            [
                str(option.get("content", "")),
                str(option.get("core_conflict", "")),
                str(option.get("key_event", "")),
                str(option.get("ending_hook", "")),
            ]
        )
        alerts = self._collect_multi_genre_drift_alerts(
            [genre],
            option_text,
            primary_genre=genre,
        )
        if not alerts:
            return 8.8, []
        penalty = min(2.8, 0.9 * len(alerts))
        return max(4.8, 8.8 - penalty), alerts

    def _score_outline_multi_genre_fit(self, genres: list[str], option: dict[str, object]) -> tuple[float, list[str]]:
        alerts = self._collect_multi_genre_drift_alerts(
            genres,
            "\n".join(
                [
                    str(option.get("content", "")),
                    str(option.get("core_conflict", "")),
                    str(option.get("key_event", "")),
                    str(option.get("ending_hook", "")),
                ]
            ),
            primary_genre=genres[0] if genres else "",
        )
        if not alerts:
            return 8.8, []
        penalty = min(2.8, 0.9 * len(alerts))
        return max(4.8, 8.8 - penalty), alerts

    def _extract_phase_signal_terms(self, values: list[str]) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for value in values:
            for raw in value.replace("/", " ").replace("|", " ").split():
                cleaned = raw.strip("，。；：、（）()[]【】!！?？\"' ")
                if len(cleaned) < 2 or len(cleaned) > 16:
                    continue
                if cleaned in seen:
                    continue
                seen.add(cleaned)
                terms.append(cleaned)
        return terms[:16]

    def _build_drafts(
        self,
        project: Project,
        task: ChapterTask | None,
        chapter_index: int,
        option: OutlineOption,
    ) -> list[ChapterDraft]:
        drafts: list[ChapterDraft] = []
        chapter = Chapter(
            id=new_id("chapter_ctx"),
            chapter_index=chapter_index,
            title=f"第 {chapter_index} 章",
            status=ChapterStatus.drafting,
            selected_option_id=option.id,
        )
        previous_issues: list[str] = []
        for revision_no in range(1, MAX_REWRITES + 2):
            if task is not None:
                self._set_task_progress(project, task, "draft_generation", f"第 {chapter_index} 章：正在生成正文（第 {revision_no} 轮）")
            query_text = self._build_draft_query(option, previous_issues)
            context_packet = self._build_context_packet(project, chapter_index, query_text, action="chapter_draft")
            if hasattr(self.agent_runner, "generate_draft_with_context"):
                draft_result = self.agent_runner.generate_draft_with_context(
                    project,
                    chapter,
                    option,
                    revision_no,
                    previous_issues,
                    context_packet,
                )
            else:
                draft_result = self.agent_runner.generate_draft(
                    project,
                    chapter,
                    option,
                    revision_no,
                    previous_issues,
                )
            if self._is_failed_draft_text(draft_result.text) or draft_result.fallback:
                review_result = AgentReviewResult(
                    score_readability=2.0,
                    score_tension=1.8,
                    score_consistency=2.2,
                    final_score=2.0,
                    issue_summary="正文生成阶段返回了兜底文本，未产出有效章节内容，当前版本不能通过。",
                    source=draft_result.source,
                    fallback=True,
                )
            else:
                if task is not None:
                    self._set_task_progress(project, task, "draft_review", f"第 {chapter_index} 章：正在评分与一致性审查（第 {revision_no} 轮）")
                if hasattr(self.agent_runner, "review_draft_with_context"):
                    review_result = self.agent_runner.review_draft_with_context(
                        project,
                        chapter,
                        option,
                        draft_result.text,
                        revision_no,
                        context_packet,
                    )
                else:
                    review_result = self.agent_runner.review_draft(
                        project,
                        chapter,
                        option,
                        draft_result.text,
                        revision_no,
                    )
                if review_result.fallback:
                    review_result = AgentReviewResult(
                        score_readability=2.4,
                        score_tension=2.2,
                        score_consistency=2.6,
                        final_score=2.4,
                        issue_summary="正文评分阶段返回了兜底结果，当前评分无效，需重新生成或人工复核。",
                        source=review_result.source,
                        fallback=True,
                    )
            consistency_alerts = self._run_consistency_checks(project, chapter, draft_result.text)
            style_alerts = self._run_style_checks(draft_result.text)
            genre_alerts = self._run_genre_checks(project, option, draft_result.text)
            conflict_alerts = self._build_conflict_alerts(project, draft_result.text)
            draft = ChapterDraft(
                id=new_id("draft"),
                revision_no=revision_no,
                content=draft_result.text,
                score_readability=review_result.score_readability,
                score_tension=review_result.score_tension,
                score_consistency=review_result.score_consistency,
                final_score=max(
                    0.0,
                    review_result.final_score
                    - 0.4 * len(consistency_alerts)
                    - STYLE_ALERT_PENALTY * len(style_alerts)
                    - GENRE_ALERT_PENALTY * len(genre_alerts),
                ),
                issue_summary=self._merge_issue_summary(review_result.issue_summary, consistency_alerts, style_alerts, genre_alerts),
                conflict_alerts=conflict_alerts,
            )
            print(
                (
                    f"[draft_revision] project_id={project.id} chapter_index={chapter_index} revision_no={revision_no} "
                    f"draft_source={draft_result.source} draft_fallback={draft_result.fallback} "
                    f"review_source={review_result.source} review_fallback={review_result.fallback} "
                    f"score={draft.final_score} text_chars={len(draft_result.text)} "
                    f"issue_summary={review_result.issue_summary[:120]!r}"
                ),
                flush=True,
            )
            drafts.append(draft)
            self.db.log(
                "agent_called",
                {
                    "project_id": project.id,
                    "chapter_index": chapter_index,
                    "action": "chapter_draft",
                    "context_packet": context_packet,
                    "source": draft_result.source,
                    "fallback": draft_result.fallback,
                    "revision_no": revision_no,
                },
            )
            self.db.log(
                "agent_called",
                {
                    "project_id": project.id,
                    "chapter_index": chapter_index,
                    "action": "chapter_review",
                    "context_packet": context_packet,
                    "source": review_result.source,
                    "fallback": review_result.fallback,
                    "revision_no": revision_no,
                },
            )
            if is_passing_score(draft.final_score):
                break
            previous_issues.append(review_result.issue_summary)
        return drafts

    def _refresh_chapter_drafts(
        self,
        project: Project,
        chapter: Chapter,
        option: OutlineOption,
    ) -> None:
        chapter.status = ChapterStatus.outline_selected
        chapter.selected_option_id = option.id
        drafts = self._build_drafts(project, None, chapter.chapter_index, option)
        for draft in drafts:
            draft.selected = False
        best = select_highest_scored_draft(drafts)
        best.selected = True
        chapter.drafts = drafts
        chapter.final_draft_id = best.id
        chapter.rewrite_count = len(drafts) - 1
        chapter.needs_manual_review = not is_passing_score(best.final_score)
        chapter.status = (
            ChapterStatus.needs_manual_review if chapter.needs_manual_review else ChapterStatus.completed
        )
        self._sync_project_memory_for_chapter(project, chapter, option, best.content)

    def _select_outline_option(self, chapter: Chapter, option_id: str) -> None:
        for option in chapter.outline_options:
            option.selected = option.id == option_id
        chapter.selected_option_id = option_id

    def _selected_outline_option(self, chapter: Chapter) -> OutlineOption:
        if chapter.selected_option_id:
            return self._get_outline_option(chapter, chapter.selected_option_id)
        if chapter.outline_options:
            return select_highest_scored_option(chapter.outline_options)
        raise DomainError("INVALID_ARGUMENT", "章节当前没有可用走向")

    def _get_outline_option(self, chapter: Chapter, option_id: str) -> OutlineOption:
        option = next((item for item in chapter.outline_options if item.id == option_id), None)
        if not option:
            raise DomainError("INVALID_ARGUMENT", "剧情走向不存在", {"option_id": option_id})
        return option

    def _assert_chapter_editable(self, chapter: Chapter) -> None:
        if chapter.confirmed_by_user:
            raise DomainError("INVALID_ARGUMENT", "章节已确认，不能继续修改")

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

    def _replace_first_match(self, chapter_content: str, paragraph: str, updated: str) -> str:
        if paragraph and paragraph in chapter_content:
            return chapter_content.replace(paragraph, updated, 1)
        if not chapter_content.strip():
            return updated
        return f"{chapter_content}\n\n{updated}"

    def _remove_first_match(self, chapter_content: str, paragraph: str) -> str:
        if paragraph not in chapter_content:
            raise DomainError("INVALID_ARGUMENT", "目标段落不存在于当前正文中")
        updated = chapter_content.replace(paragraph, "", 1)
        cleaned_lines = [line for line in updated.splitlines() if line.strip()]
        return "\n".join(cleaned_lines)

    def _selected_draft_content(self, chapter: Chapter) -> str:
        draft = next((item for item in chapter.drafts if item.selected), None)
        if draft:
            return draft.content
        return chapter.drafts[-1].content if chapter.drafts else ""

    def _is_failed_draft_text(self, value: str) -> bool:
        return value.strip() == FAILED_DRAFT_TEXT

    def _seed_character_profiles(self, character_cards: list[str]) -> list[dict[str, object]]:
        profiles: list[dict[str, object]] = []
        for card in character_cards:
            cleaned = card.strip()
            if not cleaned:
                continue
            name = cleaned.split(" ")[0].split("：")[0].strip()
            anchor_tags = self._derive_anchor_tags(cleaned)
            profiles.append(
                {
                    "name": name or cleaned,
                    "anchor": cleaned,
                    "personality_tags": anchor_tags,
                    "current_goal": "维持当前主线推进并回应章节冲突",
                    "current_state": "项目初始化阶段",
                    "appeared_chapter_indexes": [],
                    "last_seen_chapter_index": 0,
                }
            )
        return profiles

    def _seed_timeline_nodes(self, event_summary: list[str]) -> list[dict[str, object]]:
        return [
            {
                "sequence_no": index + 1,
                "summary": event,
                "chapter_index": 0,
                "source": "project_init",
            }
            for index, event in enumerate(event_summary)
        ]

    def _seed_major_events(self, event_summary: list[str]) -> list[dict[str, object]]:
        return [
            {
                "chapter_index": 0,
                "summary": event,
                "impact": "project_context",
            }
            for event in event_summary
        ]

    def _seed_fact_records(self, character_cards: list[str], event_summary: list[str]) -> list[dict[str, object]]:
        facts: list[dict[str, object]] = []
        for name in self._extract_character_names(character_cards):
            facts.append(
                {
                    "chapter_index": 0,
                    "fact_type": "character_anchor",
                    "subject": name,
                    "summary": f"{name} 的初始设定已建立",
                    "keywords": [name, "角色设定"],
                    "source": "project_init",
                }
            )
        for event in event_summary:
            facts.append(
                {
                    "chapter_index": 0,
                    "fact_type": "seed_event",
                    "subject": "主线",
                    "summary": event,
                    "keywords": self._extract_focus_terms(event, []),
                    "source": "project_init",
                }
            )
        return facts[:20]

    def _seed_story_beats(
        self,
        title: str,
        genre: str,
        summary: str,
        character_cards: list[str],
        world_rules: list[str],
        event_summary: list[str],
    ) -> list[dict[str, object]]:
        focus_name = self._extract_character_names(character_cards[:1])
        protagonist = focus_name[0] if focus_name else "主角"
        opening_pressure = event_summary[0] if event_summary else f"{title} 的局势开始出现异常变化"
        latent_risk = event_summary[-1] if event_summary else f"{protagonist} 被迫卷入更大的冲突"
        world_limit = world_rules[0] if world_rules else "世界存在必须付出代价的限制"
        return [
            {
                "phase_index": 1,
                "label": "起势阶段",
                "target_chapter_start": 1,
                "target_chapter_end": 3,
                "phase_goal": f"{protagonist} 必须主动回应眼前冲突，并完成第一轮局势判断",
                "phase_pressure": [
                    opening_pressure,
                    f"{protagonist} 不能继续停留在旁观位置",
                ],
                "required_change": [
                    f"{protagonist} 对局势的理解必须明显改变",
                    "至少一组人物关系出现新的张力或裂痕",
                ],
                "forbidden_outcomes": [
                    "不要过早揭露最终真相",
                    "不要提前彻底解决核心矛盾",
                ],
                "foreshadow_to_surface": [
                    latent_risk,
                    world_limit,
                ],
                "tone_trend": "从试探转向紧张",
                "flex_points": [
                    "具体触发事件和冲突场景允许自由生成",
                    "允许通过人物误判制造意外偏转",
                ],
                "status": "active",
            },
            {
                "phase_index": 2,
                "label": "升级阶段",
                "target_chapter_start": 4,
                "target_chapter_end": 6,
                "phase_goal": f"{protagonist} 必须付出真实代价，推动主线冲突升级",
                "phase_pressure": [
                    "外部阻力明显增强",
                    "角色选择开始反噬既有关系与资源",
                ],
                "required_change": [
                    "局势复杂度明显上升",
                    f"{protagonist} 的优势与代价同时被放大",
                ],
                "forbidden_outcomes": [
                    "不要让主角无代价轻易通关",
                    "不要让关系冲突被快速修复",
                ],
                "foreshadow_to_surface": [
                    "前期埋下的异常迹象开始形成闭环",
                    "潜在对立面开始浮出水面",
                ],
                "tone_trend": "从紧张转向压迫",
                "flex_points": [
                    "允许通过不同阵营、误会或资源竞争制造升级",
                    "阶段内桥段顺序不固定",
                ],
                "status": "pending",
            },
            {
                "phase_index": 3,
                "label": "失衡阶段",
                "target_chapter_start": 7,
                "target_chapter_end": 10,
                "phase_goal": f"{protagonist} 必须面对此前选择累积的后果，并逼近更大真相",
                "phase_pressure": [
                    "多条矛盾开始交叉碰撞",
                    "隐藏力量或制度问题无法继续回避",
                ],
                "required_change": [
                    "主角与关键他人的关系进入不可逆变化",
                    "主线真相必须明显向前推进",
                ],
                "forbidden_outcomes": [
                    "不要在阶段开头就完整揭底",
                    "不要把高潮写成信息说明",
                ],
                "foreshadow_to_surface": [
                    "前期重大伏笔至少有一条进入回收期",
                    "更大对手或更高层矛盾显影",
                ],
                "tone_trend": "从压迫转向失衡",
                "flex_points": [
                    "允许角色做出不完美决定",
                    "允许章节结尾留下新的阶段性意外",
                ],
                "status": "pending",
            },
        ]

    def _normalize_story_beats(self, story_beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(story_beats, start=1):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            phase_goal = str(item.get("phase_goal", "")).strip()
            if not label and not phase_goal:
                continue
            normalized.append(
                {
                    "phase_index": int(item.get("phase_index", index) or index),
                    "label": label or f"阶段 {index}",
                    "target_chapter_start": int(item.get("target_chapter_start", max(1, index * 3 - 2)) or max(1, index * 3 - 2)),
                    "target_chapter_end": int(item.get("target_chapter_end", index * 3) or index * 3),
                    "phase_goal": phase_goal,
                    "phase_pressure": self._normalized_string_list(item.get("phase_pressure", [])),
                    "required_change": self._normalized_string_list(item.get("required_change", [])),
                    "forbidden_outcomes": self._normalized_string_list(item.get("forbidden_outcomes", [])),
                    "foreshadow_to_surface": self._normalized_string_list(item.get("foreshadow_to_surface", [])),
                    "tone_trend": str(item.get("tone_trend", "")).strip(),
                    "flex_points": self._normalized_string_list(item.get("flex_points", [])),
                    "status": str(item.get("status", "pending")).strip() or "pending",
                }
            )
        return normalized

    def _refresh_story_planning(self, project: Project) -> None:
        if not project.memory.story_beats:
            project.memory.story_beats = self._seed_story_beats(
                project.title,
                project.genre,
                project.summary,
                project.memory.character_cards,
                project.memory.world_rules,
                project.memory.event_summary,
            )
        latest_index = max(project.memory.latest_chapter_index, max((chapter.chapter_index for chapter in project.chapters), default=0))
        project.memory.latest_chapter_index = latest_index
        for beat in project.memory.story_beats:
            start = int(beat.get("target_chapter_start", 1))
            end = int(beat.get("target_chapter_end", start))
            if latest_index >= end:
                beat["status"] = "completed"
            elif start <= latest_index + 1 <= end:
                beat["status"] = "active"
            elif latest_index + 1 < start:
                beat["status"] = "pending"
        active = next((beat for beat in project.memory.story_beats if beat.get("status") == "active"), None)
        if active is None and project.memory.story_beats:
            active = project.memory.story_beats[min(len(project.memory.story_beats) - 1, latest_index // 3)]
            active["status"] = "active"
        project.memory.active_phase = dict(active or {})

    def _sync_project_memory_for_chapter(
        self,
        project: Project,
        chapter: Chapter,
        selected: OutlineOption,
        draft_content: str,
    ) -> None:
        chapter_summary = f"第 {chapter.chapter_index} 章：{selected.key_event}"
        last_scene_snapshot = self._build_last_scene_snapshot(selected, draft_content)
        project.memory.latest_chapter_index = chapter.chapter_index
        project.memory.event_summary = [item for item in project.memory.event_summary if not item.startswith(f"第 {chapter.chapter_index} 章：")]
        project.memory.event_summary.append(chapter_summary)
        project.memory.chapter_summaries = [
            item for item in project.memory.chapter_summaries if item.get("chapter_index") != chapter.chapter_index
        ]
        project.memory.chapter_summaries.append(
            {
                "chapter_index": chapter.chapter_index,
                "summary": selected.key_event,
                "outline_hook": selected.ending_hook,
                "draft_excerpt": draft_content[:120],
                "last_scene_excerpt": last_scene_snapshot["last_scene_excerpt"],
                "last_scene_summary": last_scene_snapshot["last_scene_summary"],
                "continuity_state": last_scene_snapshot["continuity_state"],
                "hard_constraints": last_scene_snapshot["hard_constraints"],
            }
        )
        participants = self._extract_character_mentions(project.memory.character_cards, f"{selected.content}\n{draft_content}")
        if not participants:
            participants = self._extract_character_names(project.memory.character_cards[:2])
        project.memory.timeline_nodes = [item for item in project.memory.timeline_nodes if item.get("chapter_index") != chapter.chapter_index]
        project.memory.timeline_nodes.append(
            {
                "sequence_no": len(project.memory.timeline_nodes) + 1,
                "chapter_index": chapter.chapter_index,
                "summary": selected.key_event,
                "participants": participants,
                "source": chapter.id,
            }
        )
        project.memory.major_events = [item for item in project.memory.major_events if item.get("chapter_index") != chapter.chapter_index]
        project.memory.major_events.append(
            {
                "chapter_index": chapter.chapter_index,
                "summary": selected.key_event,
                "impact": selected.ending_hook,
            }
        )
        project.memory.foreshadow_threads = [
            item for item in project.memory.foreshadow_threads if item.get("introduced_chapter_index") != chapter.chapter_index
        ]
        project.memory.foreshadow_threads.append(
            {
                "title": f"第 {chapter.chapter_index} 章钩子",
                "introduced_chapter_index": chapter.chapter_index,
                "status": "open",
                "latest_progress_note": selected.ending_hook,
            }
        )
        project.memory.fact_records = [
            item for item in project.memory.fact_records if item.get("chapter_index") != chapter.chapter_index
        ]
        project.memory.fact_records.extend(
            self._extract_fact_records(project, chapter.chapter_index, selected, draft_content, participants)
        )
        self._update_character_profiles(project, chapter.chapter_index, participants, selected, draft_content)
        self._update_relationship_states(project, chapter.chapter_index, participants, selected)
        self._roll_story_beats_forward(project, chapter, selected, draft_content)
        self._refresh_story_planning(project)

    def _remove_chapter_from_memory(self, project: Project, chapter_index: int) -> None:
        project.memory.event_summary = [
            item for item in project.memory.event_summary if not item.startswith(f"第 {chapter_index} 章：")
        ]
        project.memory.chapter_summaries = [
            item for item in project.memory.chapter_summaries if item.get("chapter_index") != chapter_index
        ]
        project.memory.timeline_nodes = [
            item for item in project.memory.timeline_nodes if item.get("chapter_index") != chapter_index
        ]
        project.memory.major_events = [
            item for item in project.memory.major_events if item.get("chapter_index") != chapter_index
        ]
        project.memory.foreshadow_threads = [
            item for item in project.memory.foreshadow_threads if item.get("introduced_chapter_index") != chapter_index
        ]
        project.memory.fact_records = [
            item for item in project.memory.fact_records if item.get("chapter_index") != chapter_index
        ]
        cleaned_profiles: list[dict[str, object]] = []
        for profile in project.memory.character_profiles:
            appeared = [index for index in profile.get("appeared_chapter_indexes", []) if index != chapter_index]
            updated = dict(profile)
            updated["appeared_chapter_indexes"] = appeared
            if updated.get("last_seen_chapter_index") == chapter_index:
                updated["last_seen_chapter_index"] = max(appeared, default=0)
                if not appeared:
                    updated["latest_excerpt"] = ""
            cleaned_profiles.append(updated)
        project.memory.character_profiles = cleaned_profiles
        project.memory.relationship_states = [
            item for item in project.memory.relationship_states if item.get("chapter_index") != chapter_index
        ]
        project.memory.latest_chapter_index = max((item.chapter_index for item in project.chapters), default=0)
        self._refresh_story_planning(project)

    def _build_context_packet(
        self,
        project: Project,
        chapter_index: int,
        query_text: str,
        action: str = "chapter_draft",
    ) -> dict[str, object]:
        self._refresh_story_planning(project)
        template_guidance = self._template_guidance(project)
        previous_summary = next(
            (item for item in reversed(project.memory.chapter_summaries) if item.get("chapter_index") == chapter_index - 1),
            None,
        )
        focus_characters = self._extract_character_mentions(project.memory.character_cards, query_text)
        focus_terms = self._extract_focus_terms(query_text, focus_characters)
        recent_events = self._select_relevant_event_summaries(project, focus_characters, focus_terms)
        chapter_summaries = self._select_relevant_structured_items(
            project.memory.chapter_summaries,
            focus_characters,
            focus_terms,
            text_fields=("summary", "outline_hook", "draft_excerpt", "last_scene_summary", "last_scene_excerpt"),
        )
        if previous_summary and not any(item.get("chapter_index") == chapter_index - 1 for item in chapter_summaries):
            chapter_summaries.append(previous_summary)
            chapter_summaries = sorted(chapter_summaries, key=lambda item: int(item.get("chapter_index", 0)))[-5:]
        timeline_nodes = self._select_relevant_structured_items(
            project.memory.timeline_nodes,
            focus_characters,
            focus_terms,
            text_fields=("summary",),
            participant_fields=("participants",),
        )
        previous_timeline = next(
            (item for item in reversed(project.memory.timeline_nodes) if item.get("chapter_index") == chapter_index - 1),
            None,
        )
        if previous_timeline and not any(item.get("chapter_index") == chapter_index - 1 for item in timeline_nodes):
            timeline_nodes.append(previous_timeline)
            timeline_nodes = sorted(timeline_nodes, key=lambda item: int(item.get("chapter_index", 0)))[-5:]
        major_events = self._select_relevant_structured_items(
            project.memory.major_events,
            focus_characters,
            focus_terms,
            text_fields=("summary", "impact"),
        )
        previous_major_event = next(
            (item for item in reversed(project.memory.major_events) if item.get("chapter_index") == chapter_index - 1),
            None,
        )
        if previous_major_event and not any(item.get("chapter_index") == chapter_index - 1 for item in major_events):
            major_events.append(previous_major_event)
            major_events = sorted(major_events, key=lambda item: int(item.get("chapter_index", 0)))[-5:]
        fact_records = self._select_relevant_structured_items(
            project.memory.fact_records,
            focus_characters,
            focus_terms,
            text_fields=("subject", "summary", "fact_type"),
        )
        previous_fact_records = [
            item for item in project.memory.fact_records if item.get("chapter_index") == chapter_index - 1
        ][:3]
        if previous_fact_records:
            existing_fact_signatures = {
                (item.get("chapter_index"), item.get("fact_type"), item.get("subject"), item.get("summary"))
                for item in fact_records
            }
            for item in previous_fact_records:
                signature = (item.get("chapter_index"), item.get("fact_type"), item.get("subject"), item.get("summary"))
                if signature not in existing_fact_signatures:
                    fact_records.append(item)
            fact_records = sorted(fact_records, key=lambda item: int(item.get("chapter_index", 0)), reverse=True)[:5]
        active_foreshadows = self._select_relevant_structured_items(
            [item for item in project.memory.foreshadow_threads if item.get("status") != "resolved"],
            focus_characters,
            focus_terms,
            text_fields=("title", "latest_progress_note", "status"),
            recency_field="introduced_chapter_index",
        )
        character_profiles = self._select_relevant_character_profiles(project, focus_characters, focus_terms)
        relationship_states = self._select_relevant_relationship_states(project, focus_characters, focus_terms)
        memory_same_chapter_counts = {
            "chapter_summaries": sum(1 for item in project.memory.chapter_summaries if item.get("chapter_index") == chapter_index),
            "timeline_nodes": sum(1 for item in project.memory.timeline_nodes if item.get("chapter_index") == chapter_index),
            "major_events": sum(1 for item in project.memory.major_events if item.get("chapter_index") == chapter_index),
            "fact_records": sum(1 for item in project.memory.fact_records if item.get("chapter_index") == chapter_index),
            "foreshadow_threads": sum(
                1 for item in project.memory.foreshadow_threads if item.get("introduced_chapter_index") == chapter_index
            ),
            "character_profiles_last_seen": sum(
                1 for item in project.memory.character_profiles if item.get("last_seen_chapter_index") == chapter_index
            ),
            "relationship_states": sum(
                1 for item in project.memory.relationship_states if item.get("chapter_index") == chapter_index
            ),
        }

        def count_items_with_chapter(items: list[dict[str, object]], key: str = "chapter_index") -> int:
            return sum(1 for item in items if item.get(key) == chapter_index)

        print(
            (
                f"[context_packet] action={action} chapter_index={chapter_index} "
                f"memory_same_chapter={memory_same_chapter_counts} "
                f"selected_counts={{"
                f"'chapter_summaries': {count_items_with_chapter(chapter_summaries)}, "
                f"'timeline_nodes': {count_items_with_chapter(timeline_nodes)}, "
                f"'major_events': {count_items_with_chapter(major_events)}, "
                f"'fact_records': {count_items_with_chapter(fact_records)}, "
                f"'active_foreshadows': {count_items_with_chapter(active_foreshadows, 'introduced_chapter_index')}"
                f"}} "
                f"focus_characters={focus_characters[:5]} focus_terms={focus_terms[:10]}"
            ),
            flush=True,
        )
        if action == "chapter_review":
            packet = {
                "chapter_index": chapter_index,
                "global_outline": self._compact_text(project.memory.global_outline, 160),
                "world_rules": project.memory.world_rules[:4],
                "character_cards": project.memory.character_cards[:5],
                "character_profiles": self._compact_character_profiles(character_profiles[:4]),
                "relationship_states": self._compact_relationship_states(relationship_states[:4]),
                "recent_events": recent_events[-2:],
                "story_beats": self._compact_story_beats(project.memory.story_beats, chapter_index, limit=2),
                "active_phase": self._compact_active_phase(project.memory.active_phase),
                "chapter_summaries": self._compact_chapter_summaries(chapter_summaries[-2:]),
                "timeline_nodes": [],
                "major_events": self._compact_major_events(major_events[-2:]),
                "fact_records": self._compact_fact_records(fact_records[:3]),
                "active_foreshadows": self._compact_foreshadows(active_foreshadows[:2]),
                "retrieval_focus": {
                    "query_text": query_text,
                    "characters": focus_characters[:4],
                    "terms": focus_terms[:8],
                },
                "consistency_rules": self._build_consistency_rules(project)[:8],
                "latest_scene_bridge": self._latest_scene_bridge(project, chapter_index),
                **template_guidance,
            }
            print(
                (
                    f"[context_packet_compact] action={action} chapter_index={chapter_index} "
                    f"packet_counts={{"
                    f"'chapter_summaries': {count_items_with_chapter(packet['chapter_summaries'])}, "
                    f"'timeline_nodes': {count_items_with_chapter(packet['timeline_nodes'])}, "
                    f"'major_events': {count_items_with_chapter(packet['major_events'])}, "
                    f"'fact_records': {count_items_with_chapter(packet['fact_records'])}, "
                    f"'active_foreshadows': {count_items_with_chapter(packet['active_foreshadows'], 'introduced_chapter_index')}"
                    f"}}"
                ),
                flush=True,
            )
            return packet
        if action == "chapter_outlines":
            packet = {
                "chapter_index": chapter_index,
                "global_outline": self._compact_text(project.memory.global_outline, 220),
                "world_rules": project.memory.world_rules[:5],
                "character_cards": project.memory.character_cards[:6],
                "character_profiles": self._compact_character_profiles(character_profiles[:4]),
                "relationship_states": self._compact_relationship_states(relationship_states[:4]),
                "recent_events": recent_events[-3:],
                "story_beats": self._compact_story_beats(project.memory.story_beats, chapter_index, limit=3),
                "active_phase": self._compact_active_phase(project.memory.active_phase),
                "chapter_summaries": self._compact_chapter_summaries(chapter_summaries[-3:]),
                "timeline_nodes": self._compact_timeline_nodes(timeline_nodes[-2:]),
                "major_events": self._compact_major_events(major_events[-3:]),
                "fact_records": self._compact_fact_records(fact_records[:4]),
                "active_foreshadows": self._compact_foreshadows(active_foreshadows[:3]),
                "retrieval_focus": {
                    "query_text": query_text,
                    "characters": focus_characters[:5],
                    "terms": focus_terms[:10],
                },
                "consistency_rules": self._build_consistency_rules(project)[:8],
                "latest_scene_bridge": self._latest_scene_bridge(project, chapter_index),
                **template_guidance,
            }
            print(
                (
                    f"[context_packet_compact] action={action} chapter_index={chapter_index} "
                    f"packet_counts={{"
                    f"'chapter_summaries': {count_items_with_chapter(packet['chapter_summaries'])}, "
                    f"'timeline_nodes': {count_items_with_chapter(packet['timeline_nodes'])}, "
                    f"'major_events': {count_items_with_chapter(packet['major_events'])}, "
                    f"'fact_records': {count_items_with_chapter(packet['fact_records'])}, "
                    f"'active_foreshadows': {count_items_with_chapter(packet['active_foreshadows'], 'introduced_chapter_index')}"
                    f"}}"
                ),
                flush=True,
            )
            return packet
        packet = {
            "chapter_index": chapter_index,
            "global_outline": self._compact_text(project.memory.global_outline, 260),
            "world_rules": project.memory.world_rules[:5],
            "character_cards": project.memory.character_cards[:8],
            "character_profiles": self._compact_character_profiles(character_profiles[:5]),
            "relationship_states": self._compact_relationship_states(relationship_states[:5]),
            "recent_events": recent_events[-3:],
            "story_beats": self._compact_story_beats(project.memory.story_beats, chapter_index, limit=3),
            "active_phase": self._compact_active_phase(project.memory.active_phase),
            "chapter_summaries": self._compact_chapter_summaries(chapter_summaries[-3:]),
            "timeline_nodes": self._compact_timeline_nodes(timeline_nodes[-3:]),
            "major_events": self._compact_major_events(major_events[-3:]),
            "fact_records": self._compact_fact_records(fact_records[:5]),
            "active_foreshadows": self._compact_foreshadows(active_foreshadows[:3]),
            "retrieval_focus": {
                "query_text": query_text,
                "characters": focus_characters[:5],
                "terms": focus_terms[:10],
            },
            "consistency_rules": self._build_consistency_rules(project)[:8],
            "latest_scene_bridge": self._latest_scene_bridge(project, chapter_index),
            **template_guidance,
        }
        print(
            (
                f"[context_packet_compact] action={action} chapter_index={chapter_index} "
                f"packet_counts={{"
                f"'chapter_summaries': {count_items_with_chapter(packet['chapter_summaries'])}, "
                f"'timeline_nodes': {count_items_with_chapter(packet['timeline_nodes'])}, "
                f"'major_events': {count_items_with_chapter(packet['major_events'])}, "
                f"'fact_records': {count_items_with_chapter(packet['fact_records'])}, "
                f"'active_foreshadows': {count_items_with_chapter(packet['active_foreshadows'], 'introduced_chapter_index')}"
                f"}}"
            ),
            flush=True,
        )
        return packet

    def _template_guidance(self, project: Project) -> dict[str, str]:
        template = self.db.templates.get(project.template_id)
        if template is None:
            return {
                "style_rules": "",
                "world_template": "",
                "character_template": "",
                "outline_template": "",
            }
        return {
            "style_rules": template.style_rules.strip(),
            "world_template": template.world_template.strip(),
            "character_template": template.character_template.strip(),
            "outline_template": template.outline_template.strip(),
        }

    def _compact_text(self, value: str, limit: int) -> str:
        cleaned = value.strip()
        return cleaned[:limit]

    def _compact_character_profiles(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "name": item.get("name", ""),
                "anchor": item.get("anchor", ""),
                "current_state": item.get("current_state", ""),
                "current_goal": item.get("current_goal", ""),
                "last_seen_chapter_index": item.get("last_seen_chapter_index", 0),
            }
            for item in items
        ]

    def _compact_story_beats(self, items: list[dict[str, object]], chapter_index: int, limit: int) -> list[dict[str, object]]:
        prioritized = sorted(
            items,
            key=lambda item: (
                0 if item.get("status") == "active" else 1,
                abs(int(item.get("target_chapter_start", chapter_index)) - chapter_index),
            ),
        )
        return [
            {
                "phase_index": item.get("phase_index", 0),
                "label": item.get("label", ""),
                "status": item.get("status", ""),
                "target_chapter_start": item.get("target_chapter_start", 0),
                "target_chapter_end": item.get("target_chapter_end", 0),
                "phase_goal": item.get("phase_goal", ""),
                "required_change": list(item.get("required_change", []))[:2],
                "tone_trend": item.get("tone_trend", ""),
            }
            for item in prioritized[:limit]
        ]

    def _compact_active_phase(self, active_phase: dict[str, object]) -> dict[str, object]:
        if not active_phase:
            return {}
        return {
            "phase_index": active_phase.get("phase_index", 0),
            "label": active_phase.get("label", ""),
            "phase_goal": active_phase.get("phase_goal", ""),
            "phase_pressure": list(active_phase.get("phase_pressure", []))[:2],
            "required_change": list(active_phase.get("required_change", []))[:2],
            "forbidden_outcomes": list(active_phase.get("forbidden_outcomes", []))[:2],
            "foreshadow_to_surface": list(active_phase.get("foreshadow_to_surface", []))[:2],
            "tone_trend": active_phase.get("tone_trend", ""),
            "flex_points": list(active_phase.get("flex_points", []))[:2],
            "status": active_phase.get("status", ""),
        }

    def _roll_story_beats_forward(
        self,
        project: Project,
        chapter: Chapter,
        selected: OutlineOption,
        draft_content: str,
    ) -> None:
        if not project.memory.story_beats:
            return
        active = next((beat for beat in project.memory.story_beats if beat.get("status") == "active"), None)
        if active is None:
            return
        progress_note = f"第 {chapter.chapter_index} 章推进：{selected.key_event}"
        phase_progress = list(active.get("progress_notes", []))
        phase_progress = [note for note in phase_progress if not str(note).startswith(f"第 {chapter.chapter_index} 章推进：")]
        phase_progress.append(progress_note)
        active["progress_notes"] = phase_progress[-4:]
        remaining_required = list(active.get("required_change", []))
        if remaining_required:
            active["latest_progress_summary"] = f"{remaining_required[0]} 正在被推动。"
        active["latest_observed_hook"] = selected.ending_hook
        if chapter.chapter_index >= int(active.get("target_chapter_end", chapter.chapter_index)):
            active["status"] = "completed"
            next_pending = next((beat for beat in project.memory.story_beats if beat.get("status") == "pending"), None)
            if next_pending is not None:
                next_pending["status"] = "active"
                previous_excerpt = draft_content[:90]
                updated_pressure = list(next_pending.get("phase_pressure", []))
                if previous_excerpt:
                    updated_pressure = [f"延续上章余波：{previous_excerpt}", *updated_pressure][:3]
                next_pending["phase_pressure"] = updated_pressure

    def _compact_relationship_states(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "source": item.get("source", ""),
                "target": item.get("target", ""),
                "status": item.get("status", ""),
                "reason": self._compact_text(str(item.get("reason", "")), 80),
                "chapter_index": item.get("chapter_index", 0),
            }
            for item in items
        ]

    def _compact_chapter_summaries(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "chapter_index": item.get("chapter_index", 0),
                "summary": self._compact_text(str(item.get("summary", "")), 80),
                "outline_hook": self._compact_text(str(item.get("outline_hook", "")), 60),
                "last_scene_summary": self._compact_text(str(item.get("last_scene_summary", "")), 120),
                "last_scene_excerpt": self._compact_text(str(item.get("last_scene_excerpt", "")), 220),
                "continuity_state": dict(item.get("continuity_state", {})) if isinstance(item.get("continuity_state"), dict) else {},
                "hard_constraints": [
                    self._compact_text(str(entry), 80)
                    for entry in item.get("hard_constraints", [])[:4]
                ]
                if isinstance(item.get("hard_constraints"), list)
                else [],
            }
            for item in items
        ]

    def _compact_timeline_nodes(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "chapter_index": item.get("chapter_index", 0),
                "summary": self._compact_text(str(item.get("summary", "")), 80),
                "participants": list(item.get("participants", []))[:3] if isinstance(item.get("participants"), list) else [],
            }
            for item in items
        ]

    def _compact_major_events(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "chapter_index": item.get("chapter_index", 0),
                "summary": self._compact_text(str(item.get("summary", "")), 80),
                "impact": self._compact_text(str(item.get("impact", "")), 60),
            }
            for item in items
        ]

    def _compact_fact_records(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "chapter_index": item.get("chapter_index", 0),
                "fact_type": item.get("fact_type", ""),
                "subject": item.get("subject", ""),
                "summary": self._compact_text(str(item.get("summary", "")), 80),
            }
            for item in items
        ]

    def _compact_foreshadows(self, items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "title": item.get("title", ""),
                "status": item.get("status", ""),
                "latest_progress_note": self._compact_text(str(item.get("latest_progress_note", "")), 80),
            }
            for item in items
        ]

    def _extract_character_mentions(self, character_cards: list[str], text: str) -> list[str]:
        mentions: list[str] = []
        lowered = text.lower()
        for card in character_cards:
            name = card.split(" ")[0].strip()
            if name and name.lower() in lowered:
                mentions.append(name)
        return mentions

    def _extract_character_names(self, character_cards: list[str]) -> list[str]:
        names: list[str] = []
        for card in character_cards:
            name = card.split(" ")[0].split("：")[0].strip()
            if name and name not in names:
                names.append(name)
        return names

    def _build_outline_query(self, project: Project, chapter_index: int, user_idea: str = "") -> str:
        previous_summary = next(
            (item for item in reversed(project.memory.chapter_summaries) if item.get("chapter_index") == chapter_index - 1),
            {},
        )
        parts = [
            project.summary,
            project.memory.event_summary[-1] if project.memory.event_summary else "",
            " ".join(
                item.get("latest_progress_note", "")
                for item in project.memory.foreshadow_threads[-3:]
                if item.get("latest_progress_note")
            ),
            str(previous_summary.get("last_scene_summary", "")),
            " ".join(str(entry) for entry in previous_summary.get("hard_constraints", [])[:4])
            if isinstance(previous_summary.get("hard_constraints"), list)
            else "",
            f"第 {chapter_index} 章",
        ]
        if user_idea.strip():
            parts.append(f"用户补充想法：{user_idea.strip()}")
        return "\n".join(part for part in parts if part)

    def _build_draft_query(self, option: OutlineOption, previous_issues: list[str]) -> str:
        parts = [
            option.content,
            option.core_conflict,
            option.key_event,
            option.ending_hook,
            "；".join(previous_issues[-3:]),
        ]
        return "\n".join(part for part in parts if part)

    def _extract_focus_terms(self, text: str, focus_characters: list[str]) -> list[str]:
        normalized = (
            text.replace("\n", " ")
            .replace("，", " ")
            .replace("。", " ")
            .replace("；", " ")
            .replace("：", " ")
            .replace("、", " ")
            .replace(",", " ")
            .replace(".", " ")
        )
        terms: list[str] = []
        for token in [*focus_characters, *normalized.split(" ")]:
            cleaned = token.strip()
            if len(cleaned) >= 2 and cleaned not in terms:
                terms.append(cleaned)
        return terms[:12]

    def _select_relevant_event_summaries(
        self,
        project: Project,
        focus_characters: list[str],
        focus_terms: list[str],
    ) -> list[str]:
        scored: list[tuple[float, int, str]] = []
        for index, summary in enumerate(project.memory.event_summary):
            score = self._score_text_relevance(summary, focus_characters, focus_terms) + index * 0.05
            scored.append((score, index, summary))
        ranked = sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)
        chosen = sorted(ranked[:5], key=lambda item: item[1])
        return [item[2] for item in chosen]

    def _select_relevant_character_profiles(
        self,
        project: Project,
        focus_characters: list[str],
        focus_terms: list[str],
    ) -> list[dict[str, object]]:
        scored: list[tuple[float, int, dict[str, object]]] = []
        for index, profile in enumerate(project.memory.character_profiles):
            blob = " ".join(
                [
                    str(profile.get("name", "")),
                    str(profile.get("anchor", "")),
                    str(profile.get("current_state", "")),
                    str(profile.get("current_goal", "")),
                ]
            )
            recency = float(profile.get("last_seen_chapter_index", 0))
            score = self._score_text_relevance(blob, focus_characters, focus_terms) + recency * 0.08
            scored.append((score, index, profile))
        ranked = sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[:8]]

    def _select_relevant_relationship_states(
        self,
        project: Project,
        focus_characters: list[str],
        focus_terms: list[str],
    ) -> list[dict[str, object]]:
        scored: list[tuple[float, int, dict[str, object]]] = []
        for index, relation in enumerate(project.memory.relationship_states):
            blob = " ".join(
                [
                    str(relation.get("source", "")),
                    str(relation.get("target", "")),
                    str(relation.get("status", "")),
                    str(relation.get("reason", "")),
                ]
            )
            recency = float(relation.get("chapter_index", 0))
            score = self._score_text_relevance(blob, focus_characters, focus_terms) + recency * 0.08
            scored.append((score, index, relation))
        ranked = sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[:8]]

    def _select_relevant_structured_items(
        self,
        items: list[dict[str, object]],
        focus_characters: list[str],
        focus_terms: list[str],
        text_fields: tuple[str, ...],
        participant_fields: tuple[str, ...] = (),
        recency_field: str = "chapter_index",
    ) -> list[dict[str, object]]:
        scored: list[tuple[float, int, dict[str, object]]] = []
        for index, item in enumerate(items):
            parts = [str(item.get(field, "")) for field in text_fields]
            for field in participant_fields:
                value = item.get(field, [])
                if isinstance(value, list):
                    parts.extend(str(entry) for entry in value)
            blob = " ".join(part for part in parts if part)
            recency = float(item.get(recency_field, 0) or 0)
            score = self._score_text_relevance(blob, focus_characters, focus_terms) + recency * 0.08
            scored.append((score, index, item))
        ranked = sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)
        selected = ranked[:5]
        return [item[2] for item in sorted(selected, key=lambda entry: entry[1])]

    def _score_text_relevance(self, text: str, focus_characters: list[str], focus_terms: list[str]) -> float:
        lowered = text.lower()
        score = 0.0
        for name in focus_characters:
            if name and name.lower() in lowered:
                score += 4.0
        for term in focus_terms:
            if term and term.lower() in lowered:
                score += 1.2
        return score

    def _extract_fact_records(
        self,
        project: Project,
        chapter_index: int,
        selected: OutlineOption,
        draft_content: str,
        participants: list[str],
    ) -> list[dict[str, object]]:
        facts: list[dict[str, object]] = []
        event_keywords = self._extract_focus_terms(
            f"{selected.key_event} {selected.core_conflict} {selected.ending_hook}",
            participants,
        )
        facts.append(
            {
                "chapter_index": chapter_index,
                "fact_type": "chapter_event",
                "subject": participants[0] if participants else "主线",
                "summary": selected.key_event,
                "keywords": event_keywords,
                "source": "chapter_summary",
            }
        )
        for name in participants:
            facts.append(
                {
                    "chapter_index": chapter_index,
                    "fact_type": "character_state",
                    "subject": name,
                    "summary": f"{name} 在本章卷入“{selected.key_event}”",
                    "keywords": [name, *event_keywords[:4]],
                    "source": "character_state_sync",
                }
            )
        if len(participants) >= 2:
            facts.append(
                {
                    "chapter_index": chapter_index,
                    "fact_type": "relationship_shift",
                    "subject": f"{participants[0]}-{participants[1]}",
                    "summary": selected.core_conflict,
                    "keywords": [participants[0], participants[1], *event_keywords[:4]],
                    "source": "relationship_sync",
                }
            )
        if selected.ending_hook.strip():
            status = "resolved" if any(token in selected.ending_hook for token in ["解决", "揭晓", "真相", "落幕"]) else "open"
            facts.append(
                {
                    "chapter_index": chapter_index,
                    "fact_type": "foreshadow_progress",
                    "subject": f"第{chapter_index}章钩子",
                    "summary": selected.ending_hook,
                    "keywords": event_keywords[:6],
                    "status": status,
                    "source": "foreshadow_sync",
                }
            )
        for sentence in self._extract_fact_sentences(draft_content, participants):
            facts.append(
                {
                    "chapter_index": chapter_index,
                    "fact_type": "draft_fact",
                    "subject": sentence["subject"],
                    "summary": sentence["summary"],
                    "keywords": sentence["keywords"],
                    "source": "draft_sentence",
                }
            )
        return facts[:12]

    def _extract_fact_sentences(self, draft_content: str, participants: list[str]) -> list[dict[str, object]]:
        sentences: list[dict[str, object]] = []
        chunks = [
            part.strip()
            for part in draft_content.replace("\n", "。").split("。")
            if part.strip()
        ]
        for chunk in chunks[:8]:
            subject = next((name for name in participants if name in chunk), participants[0] if participants else "主线")
            keywords = self._extract_focus_terms(chunk, [subject] if subject else [])
            if not keywords:
                continue
            sentences.append(
                {
                    "subject": subject,
                    "summary": chunk[:80],
                    "keywords": keywords[:6],
                }
            )
        return sentences[:6]

    def _build_conflict_alerts(self, project: Project, draft_content: str) -> list[dict[str, str]]:
        alerts: list[dict[str, str]] = []
        lowered = draft_content.lower()
        conflict_pairs = [
            ("结盟", "决裂"),
            ("合作", "敌对"),
            ("信任", "背叛"),
            ("留守", "离开"),
            ("存活", "死亡"),
            ("失踪", "现身"),
            ("封存", "公开"),
            ("隐瞒", "坦白"),
        ]
        for fact in project.memory.fact_records[-30:]:
            subject = str(fact.get("subject", "")).strip()
            summary = str(fact.get("summary", "")).strip()
            if not subject or not summary or subject.lower() not in lowered:
                continue
            for positive, negative in conflict_pairs:
                has_positive_fact = positive in summary
                has_negative_fact = negative in summary
                has_positive_now = positive in draft_content
                has_negative_now = negative in draft_content
                if has_positive_fact and has_negative_now and not has_positive_now:
                    alerts.append(
                        {
                            "subject": subject,
                            "existing_fact": summary,
                            "conflict_keyword": negative,
                            "message": f"{subject} 的既有事实记录显示“{positive}”，正文却出现“{negative}”，可能存在设定冲突。",
                        }
                    )
                    break
                if has_negative_fact and has_positive_now and not has_negative_now:
                    alerts.append(
                        {
                            "subject": subject,
                            "existing_fact": summary,
                            "conflict_keyword": positive,
                            "message": f"{subject} 的既有事实记录显示“{negative}”，正文却出现“{positive}”，可能存在设定冲突。",
                        }
                    )
                    break
        deduped: list[dict[str, str]] = []
        for alert in alerts:
            if alert not in deduped:
                deduped.append(alert)
        return deduped[:4]

    def _update_character_profiles(
        self,
        project: Project,
        chapter_index: int,
        participants: list[str],
        selected: OutlineOption,
        draft_content: str,
    ) -> None:
        profiles_by_name = {str(item.get("name")): item for item in project.memory.character_profiles}
        for name in participants:
            profile = profiles_by_name.get(name)
            if not profile:
                profile = {
                    "name": name,
                    "anchor": name,
                    "current_state": "新进入剧情",
                    "appeared_chapter_indexes": [],
                    "last_seen_chapter_index": 0,
                }
                project.memory.character_profiles.append(profile)
                profiles_by_name[name] = profile
            appeared = list(profile.get("appeared_chapter_indexes", []))
            if chapter_index not in appeared:
                appeared.append(chapter_index)
            profile["appeared_chapter_indexes"] = appeared
            profile["last_seen_chapter_index"] = chapter_index
            profile["current_state"] = f"参与事件：{selected.key_event}"
            profile["current_goal"] = f"围绕“{selected.key_event}”推进个人处境"
            profile["latest_excerpt"] = draft_content[:80]

    def _build_consistency_rules(self, project: Project) -> list[str]:
        rules = [f"世界规则：{rule}" for rule in project.memory.world_rules[:5]]
        rules.extend(
            f"角色约束：{profile.get('name')} 保持 {profile.get('anchor')}"
            for profile in project.memory.character_profiles[:5]
            if profile.get("name") and profile.get("anchor")
        )
        rules.extend(
            f"关系约束：{item.get('source')} 与 {item.get('target')} 当前为 {item.get('status')}"
            for item in project.memory.relationship_states[-5:]
            if item.get("source") and item.get("target") and item.get("status")
        )
        rules.extend(
            f"近期情节：{item.get('summary')}"
            for item in project.memory.chapter_summaries[-3:]
            if item.get("summary")
        )
        latest_summary = project.memory.chapter_summaries[-1] if project.memory.chapter_summaries else {}
        if latest_summary:
            if latest_summary.get("last_scene_summary"):
                rules.append(f"承接约束：{latest_summary.get('last_scene_summary')}")
            if isinstance(latest_summary.get("hard_constraints"), list):
                rules.extend(
                    f"硬约束：{constraint}"
                    for constraint in latest_summary.get("hard_constraints", [])[:3]
                    if str(constraint).strip()
                )
        return rules

    def _run_consistency_checks(self, project: Project, chapter: Chapter, draft_content: str) -> list[str]:
        alerts: list[str] = []
        if project.memory.character_profiles:
            names = [str(item.get("name")) for item in project.memory.character_profiles if item.get("name")]
            if names and not any(name in draft_content for name in names):
                alerts.append("正文未显式承接已知主要角色，可能导致人物连续性不足。")
        for profile in project.memory.character_profiles[:5]:
            name = str(profile.get("name") or "")
            tags = [str(tag) for tag in profile.get("personality_tags", []) if str(tag).strip()]
            if name and name in draft_content and tags and not any(tag in draft_content for tag in tags):
                alerts.append(f"{name} 的性格锚点未在正文中得到体现。")
        previous_summary = next(
            (item for item in reversed(project.memory.chapter_summaries) if item.get("chapter_index") == chapter.chapter_index - 1),
            None,
        )
        if previous_summary and str(previous_summary.get("summary", "")).strip():
            keyword = str(previous_summary["summary"]).strip()[:6]
            if keyword and keyword not in draft_content:
                alerts.append("正文与上一章关键事件的衔接较弱，建议补足连续性线索。")
        alerts.extend(self._detect_scene_regression(previous_summary or {}, draft_content))
        alerts.extend(item["message"] for item in self._build_conflict_alerts(project, draft_content))
        return alerts

    def _run_style_checks(self, draft_content: str) -> list[str]:
        text = draft_content.strip()
        if not text:
            return []
        alerts: list[str] = []
        summary_markers = ["这一刻", "这一切都说明", "某种意义上", "总之", "归根结底", "仿佛预示着", "也许这就是"]
        connector_markers = ["与此同时", "然而", "而就在这时", "紧接着", "下一刻"]
        if sum(text.count(marker) for marker in summary_markers) >= 2:
            alerts.append("存在较明显的总结腔或主题先行表达，容易显得像模型在替读者概括。")
        if sum(text.count(marker) for marker in connector_markers) >= 4:
            alerts.append("段落转接过度依赖万能连接句，句式重复感偏重。")
        if "，仿佛" in text and text.count("仿佛") >= 2:
            alerts.append("比喻和感受词重复偏多，气氛推进有模板化倾向。")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        short_lines = [line for line in lines if 4 <= len(line) <= 10]
        if len(short_lines) >= 4:
            unique_lengths = {len(line) for line in short_lines[:6]}
            if len(unique_lengths) <= 2:
                alerts.append("短句排比偏密，节奏过于工整，容易形成明显 AI 腔。")
        return alerts

    def _run_genre_checks(self, project: Project, option: OutlineOption, draft_content: str) -> list[str]:
        combined = "\n".join(
            [
                option.content,
                option.core_conflict,
                option.key_event,
                option.ending_hook,
                draft_content,
            ]
        )
        return self._collect_multi_genre_drift_alerts(project.genres or [project.genre], combined, primary_genre=project.genre)

    def _collect_genre_drift_alerts(self, genre: str, text: str) -> list[str]:
        config = self.db.genre_configs.get(genre)
        required_terms = [term for term in (config.required_any if config else []) if isinstance(term, str) and term]
        forbidden_terms = [term for term in (config.forbidden_any if config else []) if isinstance(term, str) and term]
        if not required_terms and not forbidden_terms:
            return []
        alerts: list[str] = []
        required_hits = [term for term in required_terms if term in text]
        forbidden_hits = [term for term in forbidden_terms if term in text]
        if required_terms and not required_hits:
            alerts.append(f"题材主信号不足：正文缺少“{required_terms[0]}”这一类能体现当前题材核心驱动力的元素。")
        if len(forbidden_hits) >= 2:
            alerts.append(f"题材串台明显：出现了 {'、'.join(forbidden_hits[:4])} 等偏离当前题材的主导信号。")
        elif forbidden_hits and not required_hits:
            alerts.append(f"题材方向偏移：出现了“{forbidden_hits[0]}”这类异题材信号，但缺少本题材应有支撑。")
        return alerts

    def _collect_multi_genre_drift_alerts(self, genres: list[str], text: str, primary_genre: str = "") -> list[str]:
        active_genres = [item.strip() for item in genres if item.strip()]
        if not active_genres:
            active_genres = [primary_genre.strip()] if primary_genre.strip() else []
        if not active_genres:
            return []
        lead_genre = primary_genre.strip() or active_genres[0]
        alerts = self._collect_genre_drift_alerts(lead_genre, text)
        if len(active_genres) <= 1:
            return alerts
        lead_config = self.db.genre_configs.get(lead_genre)
        lead_required = [term for term in (lead_config.required_any if lead_config else []) if term]
        lead_hits = [term for term in lead_required if term in text]
        support_hits: list[str] = []
        for genre in active_genres[1:]:
            support_config = self.db.genre_configs.get(genre)
            for term in (support_config.required_any if support_config else []):
                if term and term in text and term not in support_hits:
                    support_hits.append(term)
        if support_hits and not lead_hits:
            alerts.append(f"多题材失衡：副题材信号（如 {support_hits[0]}）已进入主导，但主题材“{lead_genre}”的核心驱动力没有立住。")
        return alerts

    def _build_last_scene_snapshot(self, selected: OutlineOption, draft_content: str) -> dict[str, object]:
        tail = draft_content.strip()[-260:]
        progress_value = self._extract_max_progress_value(draft_content)
        hard_constraints: list[str] = []
        if progress_value is not None and progress_value >= 1:
            hard_constraints.append(f"同步/进度类事件已推进至至少 {progress_value}% ，后续不可无解释重置为更低阶段。")
        if any(token in draft_content for token in ["意识被", "白光里", "失去意识", "昏了过去", "彻底拽进"]):
            hard_constraints.append("上一章结尾已出现强制意识牵引或失能状态，下一章必须解释恢复过程。")
        if any(token in draft_content for token in ["不可中断", "锁死", "封闭", "回收启动"]):
            hard_constraints.append("上一章明确存在强制流程或封闭状态，下一章不可直接跳回流程起点。")
        summary = selected.ending_hook.strip() or selected.key_event.strip() or tail[:80]
        return {
            "last_scene_excerpt": tail,
            "last_scene_summary": summary,
            "continuity_state": {
                "max_progress_percent": progress_value,
                "has_forced_consciousness_pull": any(token in draft_content for token in ["意识被", "白光里", "彻底拽进"]),
                "has_non_interruptible_process": any(token in draft_content for token in ["不可中断", "锁死", "回收启动"]),
            },
            "hard_constraints": hard_constraints,
        }

    def _latest_scene_bridge(self, project: Project, chapter_index: int) -> dict[str, object]:
        previous_summary = next(
            (item for item in reversed(project.memory.chapter_summaries) if item.get("chapter_index") == chapter_index - 1),
            {},
        )
        if not previous_summary:
            return {}
        return {
            "previous_chapter_index": previous_summary.get("chapter_index", 0),
            "last_scene_summary": previous_summary.get("last_scene_summary", ""),
            "last_scene_excerpt": self._compact_text(str(previous_summary.get("last_scene_excerpt", "")), 260),
            "continuity_state": dict(previous_summary.get("continuity_state", {}))
            if isinstance(previous_summary.get("continuity_state"), dict)
            else {},
            "hard_constraints": list(previous_summary.get("hard_constraints", []))[:4]
            if isinstance(previous_summary.get("hard_constraints"), list)
            else [],
        }

    def _extract_max_progress_value(self, text: str) -> int | None:
        matches: list[int] = []
        for chunk in text.replace("％", "%").split("%"):
            digits = ""
            for char in reversed(chunk):
                if char.isdigit():
                    digits = char + digits
                elif digits:
                    break
            if digits:
                try:
                    value = int(digits)
                except ValueError:
                    continue
                if 0 <= value <= 100:
                    matches.append(value)
        return max(matches) if matches else None

    def _detect_scene_regression(self, previous_summary: dict[str, object], draft_content: str) -> list[str]:
        if not previous_summary:
            return []
        alerts: list[str] = []
        continuity_state = previous_summary.get("continuity_state", {})
        if not isinstance(continuity_state, dict):
            continuity_state = {}
        previous_progress = continuity_state.get("max_progress_percent")
        current_progress = self._extract_max_progress_value(draft_content)
        if (
            isinstance(previous_progress, int)
            and previous_progress >= 40
            and current_progress is not None
            and current_progress + 20 < previous_progress
        ):
            alerts.append("正文出现明显进度回退：上一章已推进到更高阶段，本章却无解释地回到更低进度。")
        previous_excerpt = str(previous_summary.get("last_scene_excerpt", ""))
        if previous_excerpt:
            regression_markers = ["能量罩完全合拢", "同步开始", "进度条从0%", "显示屏亮起同步进度条", "刚开始同步"]
            if any(marker in draft_content for marker in regression_markers):
                progressed_markers = ["72%", "58%", "43%", "意识被", "白光里", "不可中断", "回收启动"]
                if any(marker in previous_excerpt for marker in progressed_markers):
                    alerts.append("正文疑似把上一章已推进的场景重新写成起始状态，存在时间线回卷。")
        if continuity_state.get("has_forced_consciousness_pull") and any(
            marker in draft_content for marker in ["站在他对面", "后退一步", "开口解释", "同步刚开始"]
        ):
            alerts.append("上一章已进入强制意识牵引/失能状态，本章却直接回到可自由对话阶段，缺少恢复解释。")
        return alerts

    def _merge_issue_summary(
        self,
        issue_summary: str,
        alerts: list[str],
        style_alerts: list[str] | None = None,
        genre_alerts: list[str] | None = None,
    ) -> str:
        if not alerts and not style_alerts and not genre_alerts:
            return issue_summary
        fragments = [issue_summary]
        if alerts:
            fragments.append(f"一致性提醒：{'；'.join(alerts)}")
        if style_alerts:
            fragments.append(f"表达提醒：{'；'.join(style_alerts)}")
        if genre_alerts:
            fragments.append(f"题材提醒：{'；'.join(genre_alerts)}")
        return " ".join(item for item in fragments if item)

    def _derive_anchor_tags(self, anchor: str) -> list[str]:
        tags: list[str] = []
        for token in ["冷静", "克制", "冲动", "骄傲", "多疑", "善良", "狠厉", "隐忍", "执拗", "谨慎", "温柔"]:
            if token in anchor:
                tags.append(token)
        return tags

    def _update_relationship_states(
        self,
        project: Project,
        chapter_index: int,
        participants: list[str],
        selected: OutlineOption,
    ) -> None:
        resolved_participants = list(participants)
        if len(resolved_participants) < 2:
            for name in self._extract_character_names(project.memory.character_cards):
                if name not in resolved_participants:
                    resolved_participants.append(name)
                if len(resolved_participants) >= 2:
                    break
        if len(resolved_participants) < 2:
            return
        source = resolved_participants[0]
        target = resolved_participants[1]
        relationship = {
            "source": source,
            "target": target,
            "status": "冲突升级" if "冲突" in selected.core_conflict else "共同卷入事件",
            "chapter_index": chapter_index,
            "reason": selected.core_conflict,
        }
        project.memory.relationship_states = [
            item
            for item in project.memory.relationship_states
            if not (item.get("source") == source and item.get("target") == target)
        ]
        project.memory.relationship_states.append(relationship)

    def _merge_string_lists(self, existing: list[str], generated: list[str]) -> list[str]:
        merged: list[str] = []
        for item in [*existing, *generated]:
            cleaned = str(item).strip()
            if cleaned and cleaned not in merged:
                merged.append(cleaned)
        return merged

    def _normalized_string_list(self, values: object) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for item in values:
            cleaned = str(item).strip()
            if cleaned:
                normalized.append(cleaned)
        return normalized

    def _merge_summary(self, existing: str, generated: str) -> str:
        if not existing:
            return generated
        if not generated:
            return existing
        return f"{existing}\n\n补充设定：{generated}"

    def _default_foundation_bundle(self, genre: str, title: str) -> dict[str, list[str] | str]:
        defaults = {
            "fantasy": {
                "character_cards": ["主角", "对手"],
                "world_rules": ["规则一", "规则二"],
                "event_summary": ["事件一", "事件二"],
                "summary": f"{title}围绕失落秩序、代价魔法与权力裂变展开，主角必须在真相与牺牲之间作出选择。",
            },
            "romance": {
                "character_cards": ["主角", "关键对象"],
                "world_rules": ["规则一", "规则二"],
                "event_summary": ["事件一", "事件二"],
                "summary": f"{title}聚焦高压处境下的情感拉扯与关系重建。",
            },
            "horror": {
                "character_cards": ["主角", "对手"],
                "world_rules": ["规则一", "规则二"],
                "event_summary": ["事件一", "事件二"],
                "summary": f"{title}以逐步逼近的未知威胁推进剧情。",
            },
        }
        return defaults.get(
            genre,
            {
                "character_cards": ["主角", "对手"],
                "world_rules": ["规则一", "规则二"],
                "event_summary": ["事件一", "事件二"],
                "summary": f"{title}围绕角色目标、外部冲突与持续升级的选择代价展开。",
            },
        )

    def _get_task(self, project: Project, task_id: str) -> ChapterTask:
        task = next((item for item in project.tasks if item.id == task_id), None)
        if not task:
            raise DomainError("INVALID_ARGUMENT", "任务不存在", {"task_id": task_id})
        return task

    def _get_chapter(self, project: Project, chapter_id: str) -> Chapter:
        chapter = next((item for item in project.chapters if item.id == chapter_id), None)
        if not chapter:
            raise DomainError("INVALID_ARGUMENT", "章节不存在", {"chapter_id": chapter_id})
        return chapter

    def get_chapter_detail(self, user_id: str, project_id: str, chapter_id: str) -> dict[str, object]:
        project = self.get_project(user_id, project_id)
        chapter = self._get_chapter(project, chapter_id)
        chapter_index = chapter.chapter_index
        owner_task = None
        for task in reversed(project.tasks):
            start = int(task.start_chapter_index)
            requested = int(task.requested_chapter_count)
            current = int(task.current_chapter_index)
            end_exclusive = min(current, start + requested)
            if start <= chapter_index < end_exclusive:
                owner_task = task
                break
        if owner_task is None:
            owner_task = next((task for task in reversed(project.tasks) if chapter_id in task.chapter_ids), None)
        return {
            "chapter": chapter,
            "task": owner_task,
            "memory": project.memory,
        }


def to_http_exception(error: DomainError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": error.code, "message": error.message, "details": error.details})
