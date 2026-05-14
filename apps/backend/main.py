from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from apps.backend.models import (
    ApiEnvelope,
    AuthLoginRequest,
    AuthPasswordChangeRequest,
    AuthRegisterRequest,
    ChapterDraftUpdateRequest,
    ChapterUpdateRequest,
    ChapterTransformRequest,
    ErrorResponse,
    GenreConfigUpsertRequest,
    MembershipPlanUpsertRequest,
    OutlineRegenerateRequest,
    OutlineOptionUpdateRequest,
    OrderUpsertRequest,
    ProjectCreate,
    ProjectFoundationRequest,
    TaskCreateRequest,
    Template,
    UserRole,
    new_id,
)
from apps.backend.auth_store import build_auth_store
from apps.backend.services import DomainError, NovelService
from apps.backend.store import store

app = FastAPI(title="智能小说协同生成平台 MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
service = NovelService(store)
auth_store = build_auth_store()
ADMIN_ROLE_HEADER = "X-User-Role"
ADMIN_ROLE_VALUE = "admin"

print(
    (
        f"[startup] AGENT_RUNNER_COMMAND={os.getenv('AGENT_RUNNER_COMMAND', '').strip() or '<default>'} "
        f"AGENT_RUNNER_URL={os.getenv('AGENT_RUNNER_URL', '').strip() or '<empty>'}"
    ),
    flush=True,
)


class QuotaAdjustRequest(BaseModel):
    target_user_id: str | None = None
    daily_delta: int = 0
    monthly_delta: int = 0
    bonus_delta: int = 0


def request_id() -> str:
    return f"req_{uuid4().hex[:8]}"


def ok(data: Any) -> dict[str, Any]:
    return ApiEnvelope(data=data, request_id=request_id()).model_dump(mode="json")


def resolve_auth_user(request: Request):
    authorization = request.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            return auth_store.get_user_by_token(token)
    return None


def require_admin(request: Request) -> None:
    user = resolve_auth_user(request)
    if user is None:
        raise DomainError("FORBIDDEN", "后台接口仅限管理员访问", status_code=403)
    if user.role == UserRole.admin:
        return
    raise DomainError("FORBIDDEN", "当前账号没有管理员权限", status_code=403)


def require_user(request: Request):
    user = resolve_auth_user(request)
    if user is None:
        raise DomainError("FORBIDDEN", "当前未登录", status_code=403)
    return user


def resolve_target_user_id(raw_value: str | None) -> str | None:
    candidate = (raw_value or "").strip()
    if not candidate:
        return None
    matched_user = auth_store.get_user_by_username(candidate)
    if matched_user is not None:
        print(
            f"[quota_target] resolved username={candidate} to user_id={matched_user.id}",
            flush=True,
        )
        return matched_user.id
    print(f"[quota_target] using raw target_user_id={candidate}", flush=True)
    return candidate


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, error: DomainError) -> JSONResponse:
    payload = ErrorResponse(
        code=error.code,
        message=error.message,
        details=error.details,
        request_id=request_id(),
    )
    return JSONResponse(status_code=error.status_code, content=payload.model_dump(mode="json"))


@app.get("/health")
async def health() -> dict[str, Any]:
    return ok({"status": "ok"})


@app.post("/api/auth/register")
async def register(payload: AuthRegisterRequest) -> dict[str, Any]:
    if payload.role != UserRole.creator:
        raise DomainError("FORBIDDEN", "公开注册仅允许创建创作者账号", status_code=403)
    try:
        user = auth_store.register_user(payload.username, payload.password, payload.role)
    except ValueError as exc:
        raise DomainError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise DomainError("INVALID_ARGUMENT", "用户名已存在或注册失败", {"reason": str(exc)}) from exc
    return ok(user)


@app.post("/api/auth/login")
async def login(payload: AuthLoginRequest) -> dict[str, Any]:
    try:
        session = auth_store.login(payload.username, payload.password)
    except ValueError as exc:
        raise DomainError("INVALID_ARGUMENT", str(exc)) from exc
    if not session:
        raise DomainError("INVALID_ARGUMENT", "用户名或密码错误")
    return ok(session)


@app.get("/api/auth/me")
async def me(request: Request) -> dict[str, Any]:
    user = resolve_auth_user(request)
    if not user:
        raise DomainError("FORBIDDEN", "当前未登录", status_code=403)
    store.migrate_user_state_alias(user.id, user.username)
    return ok(user)


@app.post("/api/auth/logout")
async def logout(request: Request) -> dict[str, Any]:
    authorization = request.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            auth_store.delete_session(token)
    return ok({"ok": True})


@app.post("/api/auth/password")
async def change_password(payload: AuthPasswordChangeRequest, request: Request) -> dict[str, Any]:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization.lower().startswith("bearer "):
        raise DomainError("FORBIDDEN", "当前未登录", status_code=403)
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise DomainError("FORBIDDEN", "当前未登录", status_code=403)
    try:
        session = auth_store.update_password(token, payload.current_password, payload.new_password)
    except ValueError as exc:
        message = str(exc)
        status_code = 403 if "失效" in message else 400
        raise DomainError("INVALID_ARGUMENT", message, status_code=status_code) from exc
    return ok(session)


@app.post("/api/projects")
<<<<<<< HEAD
async def create_project(payload: ProjectCreate, request: Request) -> dict[str, Any]:
    user = require_user(request)
    print(
        (
            f"[api] create_project user_id={user.id} username={user.username} "
            f"title={payload.title!r} genre={payload.genre!r} length_type={payload.length_type!r} "
            f"template_id={payload.template_id!r} mode_default={payload.mode_default!s} "
            f"character_cards={len(payload.character_cards)} world_rules={len(payload.world_rules)} "
            f"event_summary={len(payload.event_summary)}"
        ),
        flush=True,
    )
    return ok(await run_in_threadpool(service.create_project, user.id, payload))


@app.post("/api/projects/generate-foundation")
async def generate_project_foundation(payload: ProjectFoundationRequest, request: Request) -> dict[str, Any]:
    user = require_user(request)
    task = await run_in_threadpool(service.create_project_foundation_task, user.id, payload)
    return ok({"task_id": task.id, "status": task.status})


@app.get("/api/projects/foundation-tasks/{task_id}")
async def get_project_foundation_task(task_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    task = await run_in_threadpool(service.get_project_foundation_task, user.id, task_id)
    return ok(task)


@app.get("/api/projects")
async def list_projects(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.list_projects, user.id))


@app.get("/api/genres")
async def list_genres() -> dict[str, Any]:
    return ok(await run_in_threadpool(service.list_genres))


@app.get("/admin/genres")
async def admin_list_genres(request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(service.list_genre_configs))


@app.put("/admin/genres/{genre_value}")
async def admin_upsert_genre(genre_value: str, payload: GenreConfigUpsertRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(
        await run_in_threadpool(
            service.upsert_genre_config,
            genre_value,
            payload.label,
            payload.required_any,
            payload.forbidden_any,
        )
    )


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    store.migrate_user_state_alias(user.id, user.username)
    project = await run_in_threadpool(service.get_project, user.id, project_id)
=======
async def create_project(payload: ProjectCreate) -> dict[str, Any]:
    return ok(service.create_project(payload))


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    project = service.get_project(project_id)
>>>>>>> new-origin/main
    return ok(
        {
            "project": project,
            "quota": store.get_user_quota(user.id),
            "copyright_notice": store.safety_policy.copyright_notice,
        }
    )


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    await run_in_threadpool(service.delete_project, user.id, project_id)
    return ok({"ok": True})


@app.post("/api/projects/{project_id}/chapters/generate")
<<<<<<< HEAD
async def create_task(project_id: str, payload: TaskCreateRequest, request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.create_task, user.id, project_id, payload))


@app.post("/api/projects/{project_id}/tasks/{task_id}/run")
async def run_task(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.run_task, user.id, project_id, task_id))


@app.get("/api/projects/{project_id}/tasks/{task_id}")
async def get_task(project_id: str, task_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    project = await run_in_threadpool(service.get_project, user.id, project_id)
    task = next((task for task in project.tasks if task.id == task_id), None)
    if task is None:
      raise DomainError("INVALID_ARGUMENT", "任务不存在", {"task_id": task_id})
=======
async def create_task(project_id: str, payload: TaskCreateRequest) -> dict[str, Any]:
    return ok(service.create_task(project_id, payload))


@app.post("/api/projects/{project_id}/tasks/{task_id}/run")
async def run_task(project_id: str, task_id: str) -> dict[str, Any]:
    return ok(service.run_task(project_id, task_id))


@app.get("/api/projects/{project_id}/tasks/{task_id}")
async def get_task(project_id: str, task_id: str) -> dict[str, Any]:
    project = service.get_project(project_id)
    task = next(task for task in project.tasks if task.id == task_id)
>>>>>>> new-origin/main
    chapters = [chapter for chapter in project.chapters if chapter.id in task.chapter_ids]
    return ok({"task": task, "chapters": chapters, "memory": project.memory})


@app.get("/api/projects/{project_id}/chapters/{chapter_id}")
async def get_chapter_detail(project_id: str, chapter_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    detail = await run_in_threadpool(service.get_chapter_detail, user.id, project_id, chapter_id)
    return ok(detail)


@app.post("/api/projects/{project_id}/tasks/clear-active")
async def clear_active_task(project_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    project = await run_in_threadpool(service.clear_active_task, user.id, project_id)
    return ok({"project": project})


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/confirm")
<<<<<<< HEAD
async def confirm_chapter(project_id: str, chapter_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.confirm_chapter, user.id, project_id, chapter_id))


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/outlines/regenerate")
async def regenerate_chapter_outlines(
    project_id: str,
    chapter_id: str,
    payload: OutlineRegenerateRequest,
    request: Request,
) -> dict[str, Any]:
    user = require_user(request)
    print(f"[api] regenerate_chapter_outlines project_id={project_id} chapter_id={chapter_id} user_id={user.id}", flush=True)
    return ok(
        await run_in_threadpool(
            service.regenerate_chapter_outlines,
            user.id,
            project_id,
            chapter_id,
            payload.user_idea,
        )
    )


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/outlines/{option_id}/select")
async def select_outline_option(project_id: str, chapter_id: str, option_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    print(f"[api] select_outline_option project_id={project_id} chapter_id={chapter_id} option_id={option_id} user_id={user.id}", flush=True)
    return ok(await run_in_threadpool(service.select_outline_option, user.id, project_id, chapter_id, option_id))


@app.patch("/api/projects/{project_id}/chapters/{chapter_id}/outlines/{option_id}")
async def update_outline_option(
    project_id: str,
    chapter_id: str,
    option_id: str,
    payload: OutlineOptionUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    user = require_user(request)
    print(f"[api] update_outline_option project_id={project_id} chapter_id={chapter_id} option_id={option_id} user_id={user.id}", flush=True)
    return ok(
        await run_in_threadpool(
            service.update_outline_option,
            user.id,
            project_id,
            chapter_id,
            option_id,
            payload.content,
            payload.core_conflict,
            payload.key_event,
            payload.ending_hook,
        )
    )


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/drafts/regenerate")
async def regenerate_chapter_draft(project_id: str, chapter_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    print(f"[api] regenerate_chapter_draft project_id={project_id} chapter_id={chapter_id} user_id={user.id}", flush=True)
    return ok(await run_in_threadpool(service.regenerate_chapter_draft, user.id, project_id, chapter_id))


@app.patch("/api/projects/{project_id}/chapters/{chapter_id}/drafts/{draft_id}")
async def update_chapter_draft(
    project_id: str,
    chapter_id: str,
    draft_id: str,
    payload: ChapterDraftUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    _ = draft_id
    user = require_user(request)
    print(f"[api] update_chapter_draft project_id={project_id} chapter_id={chapter_id} draft_id={draft_id} user_id={user.id}", flush=True)
    return ok(await run_in_threadpool(service.update_chapter_draft, user.id, project_id, chapter_id, payload.content))


@app.patch("/api/projects/{project_id}/chapters/{chapter_id}")
async def update_chapter(project_id: str, chapter_id: str, payload: ChapterUpdateRequest, request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.update_chapter_title, user.id, project_id, chapter_id, payload.title))


@app.delete("/api/projects/{project_id}/chapters/{chapter_id}")
async def delete_chapter(project_id: str, chapter_id: str, request: Request) -> dict[str, Any]:
    user = require_user(request)
    project = await run_in_threadpool(service.delete_chapter, user.id, project_id, chapter_id)
    return ok({"project": project})
=======
async def confirm_chapter(project_id: str, chapter_id: str) -> dict[str, Any]:
    return ok(service.confirm_chapter(project_id, chapter_id))
>>>>>>> new-origin/main


@app.get("/api/chapters/{chapter_id}/outline-options")
async def get_outline_options(chapter_id: str) -> dict[str, Any]:
<<<<<<< HEAD
    chapter = await run_in_threadpool(
        lambda: next(
            chapter
            for project in store.projects.values()
            for chapter in project.chapters
            if chapter.id == chapter_id
        )
=======
    chapter = next(
        chapter
        for project in store.projects.values()
        for chapter in project.chapters
        if chapter.id == chapter_id
>>>>>>> new-origin/main
    )
    return ok(chapter.outline_options)


@app.get("/api/chapters/{chapter_id}/drafts")
async def get_drafts(chapter_id: str) -> dict[str, Any]:
<<<<<<< HEAD
    chapter = await run_in_threadpool(
        lambda: next(
            chapter
            for project in store.projects.values()
            for chapter in project.chapters
            if chapter.id == chapter_id
        )
=======
    chapter = next(
        chapter
        for project in store.projects.values()
        for chapter in project.chapters
        if chapter.id == chapter_id
>>>>>>> new-origin/main
    )
    return ok(
        {
            "drafts": chapter.drafts,
            "final_draft_id": chapter.final_draft_id,
            "needs_manual_review": chapter.needs_manual_review,
            "rewrite_count": chapter.rewrite_count,
        }
    )


<<<<<<< HEAD
@app.post("/api/projects/{project_id}/chapters/{chapter_id}/rewrite")
async def rewrite_chapter(project_id: str, chapter_id: str, payload: ChapterTransformRequest, request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.rewrite_chapter, user.id, project_id, chapter_id, payload))


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/expand")
async def expand_chapter(project_id: str, chapter_id: str, payload: ChapterTransformRequest, request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.expand_chapter, user.id, project_id, chapter_id, payload))


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/remove")
async def remove_chapter_paragraph(project_id: str, chapter_id: str, payload: ChapterTransformRequest, request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.remove_chapter_paragraph, user.id, project_id, chapter_id, payload))


@app.get("/api/templates")
async def list_templates(request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.list_templates, user.id, user.username))


@app.post("/api/templates")
async def create_template(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    user = require_user(request)
    genres = [str(item).strip() for item in payload.get("genres", []) if str(item).strip()]
    genre = str(payload.get("genre", "")).strip() or (genres[0] if genres else "fantasy")
    if not genres:
        genres = [genre]
=======
@app.post("/api/projects/{project_id}/chapters/{chapter_id}/paragraph-rewrite")
async def rewrite_paragraph(project_id: str, chapter_id: str, payload: RewriteRequest) -> dict[str, Any]:
    return ok(service.rewrite_paragraph(project_id, chapter_id, payload))


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/paragraph-expand")
async def expand_paragraph(project_id: str, chapter_id: str, payload: RewriteRequest) -> dict[str, Any]:
    return ok(service.expand_paragraph(project_id, chapter_id, payload))


@app.get("/api/templates")
async def list_templates() -> dict[str, Any]:
    return ok(service.list_templates())


@app.post("/api/templates")
async def create_template(payload: dict[str, Any]) -> dict[str, Any]:
>>>>>>> new-origin/main
    template = Template(
        id=new_id("template"),
        name=payload["name"],
        genre=genre,
        genres=genres,
        tags=[str(item).strip() for item in payload.get("tags", []) if str(item).strip()],
        style_rules=payload["style_rules"],
        world_template=payload["world_template"],
        character_template=payload["character_template"],
        outline_template=payload["outline_template"],
        status=payload.get("status", "draft"),
        owner_type="user",
    )
    return ok(await run_in_threadpool(service.create_template, user.id, template, user.username))


@app.patch("/api/templates/{template_id}")
async def update_template(template_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    user = require_user(request)
    return ok(await run_in_threadpool(service.update_template, user.id, template_id, payload, user.username))


@app.get("/api/membership/quotas")
<<<<<<< HEAD
async def get_quotas(request: Request) -> dict[str, Any]:
    user = require_user(request)
    store.migrate_user_state_alias(user.id, user.username)
    quota = await run_in_threadpool(store.refresh_quota_periods, user.id)
    active_plan_id = store.get_user_active_plan_id(user.id)
    print(
        (
            f"[quota_read] username={user.username} user_id={user.id} "
            f"quota={quota.model_dump()} active_plan_id={active_plan_id}"
        ),
        flush=True,
    )
    return ok(
        {
            "quota": quota,
            "default_plan": store.membership_plans[store.active_plan_id],
            "user_plan": store.membership_plans[active_plan_id],
        }
    )


@app.get("/admin/templates")
async def admin_templates(request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(lambda: list(store.templates.values())))


@app.post("/admin/templates/{template_id}/publish")
async def admin_publish_template(template_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(service.publish_template, template_id))


@app.get("/admin/memberships")
async def admin_memberships(request: Request, target_user_id: str | None = None) -> dict[str, Any]:
    require_admin(request)
    resolved_user_id = resolve_target_user_id(target_user_id)
    return ok(await run_in_threadpool(service.list_membership_plans, resolved_user_id))


@app.get("/admin/users")
async def admin_users(request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(auth_store.list_users))


@app.post("/admin/users")
async def admin_create_user(payload: AuthRegisterRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    if payload.role != UserRole.creator:
        raise DomainError("INVALID_ARGUMENT", "后台这里只允许创建创作者账号")
    try:
        user = await run_in_threadpool(auth_store.register_user, payload.username, payload.password, payload.role)
    except ValueError as exc:
        raise DomainError("INVALID_ARGUMENT", str(exc)) from exc
    return ok(user)


@app.post("/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(user_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    try:
        user = await run_in_threadpool(auth_store.admin_reset_password, user_id, "11111111")
    except ValueError as exc:
        raise DomainError("INVALID_ARGUMENT", str(exc)) from exc
    return ok({"user": user, "reset_password": "11111111"})


@app.post("/admin/memberships/plans")
async def admin_create_membership_plan(payload: MembershipPlanUpsertRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(
        await run_in_threadpool(
            service.create_membership_plan,
            payload.name,
            payload.daily_free_chapters,
            payload.monthly_free_chapters,
            payload.description,
        )
    )


@app.patch("/admin/memberships/plans/{plan_id}")
async def admin_update_membership_plan(
    plan_id: str,
    payload: MembershipPlanUpsertRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(service.update_membership_plan, plan_id, payload.model_dump()))


@app.post("/admin/memberships/plans/{plan_id}/activate")
async def admin_activate_membership_plan(plan_id: str, request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(service.activate_membership_plan, plan_id))


@app.post("/admin/quotas/adjust")
async def admin_adjust_quota(payload: QuotaAdjustRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    resolved_user_id = resolve_target_user_id(payload.target_user_id)
    return ok(
        await run_in_threadpool(
            service.adjust_quota,
            payload.daily_delta,
            payload.monthly_delta,
            payload.bonus_delta,
            resolved_user_id,
        )
    )


@app.get("/admin/orders")
async def admin_orders(request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(service.list_orders))


@app.post("/admin/orders")
async def admin_create_order(payload: OrderUpsertRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(service.create_order, payload.plan_id, payload.amount, payload.status, payload.note))


@app.patch("/admin/orders/{order_id}")
async def admin_update_order(order_id: str, payload: OrderUpsertRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    return ok(await run_in_threadpool(service.update_order, order_id, payload.model_dump()))


@app.get("/admin/safety/policies")
async def admin_safety_policies(request: Request) -> dict[str, Any]:
    require_admin(request)
=======
async def get_quotas() -> dict[str, Any]:
    return ok({"quota": store.user_quota, "plan": list(store.membership_plans.values())[0]})


@app.get("/admin/templates")
async def admin_templates() -> dict[str, Any]:
    return ok(service.list_templates())


@app.post("/admin/templates/{template_id}/publish")
async def admin_publish_template(template_id: str) -> dict[str, Any]:
    return ok(service.publish_template(template_id))


@app.get("/admin/memberships")
async def admin_memberships() -> dict[str, Any]:
    return ok({"plans": list(store.membership_plans.values()), "quota": store.user_quota})


@app.post("/admin/quotas/adjust")
async def admin_adjust_quota(payload: QuotaAdjustRequest) -> dict[str, Any]:
    return ok(service.adjust_quota(payload.free_delta, payload.monthly_delta))


@app.get("/admin/orders")
async def admin_orders() -> dict[str, Any]:
    return ok(list(store.orders.values()))


@app.get("/admin/safety/policies")
async def admin_safety_policies() -> dict[str, Any]:
>>>>>>> new-origin/main
    return ok(store.safety_policy)


@app.patch("/admin/safety/policies/{policy_id}")
<<<<<<< HEAD
async def admin_update_safety_policy(policy_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    require_admin(request)
=======
async def admin_update_safety_policy(policy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
>>>>>>> new-origin/main
    if store.safety_policy.id != policy_id:
        raise DomainError("INVALID_ARGUMENT", "策略不存在", {"policy_id": policy_id})
    store.safety_policy.blocked_terms = payload.get("blocked_terms", store.safety_policy.blocked_terms)
    store.safety_policy.copyright_notice = payload.get(
        "copyright_notice",
        store.safety_policy.copyright_notice,
    )
    store.save_safety_policy()
    store.log("safety_policy_updated", {"policy_id": policy_id})
    return ok(store.safety_policy)


@app.get("/admin/logs/tasks")
<<<<<<< HEAD
async def admin_task_logs(request: Request) -> dict[str, Any]:
    require_admin(request)
=======
async def admin_task_logs() -> dict[str, Any]:
>>>>>>> new-origin/main
    return ok(store.audit_logs)
