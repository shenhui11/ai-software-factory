from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from apps.backend.models import ApiEnvelope, ErrorResponse, ProjectCreate, RewriteRequest, TaskCreateRequest, Template, new_id
from apps.backend.services import DomainError, NovelService
from apps.backend.store import store

app = FastAPI(title="Novel Workshop MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
service = NovelService(store)


class QuotaAdjustRequest(BaseModel):
    free_delta: int = 0
    monthly_delta: int = 0


def request_id() -> str:
    return f"req_{uuid4().hex[:8]}"


def ok(data: Any) -> dict[str, Any]:
    return ApiEnvelope(data=data, request_id=request_id()).model_dump(mode="json")


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, error: DomainError) -> JSONResponse:
    payload = ErrorResponse(
        code=error.code,
        message=error.message,
        details=error.details,
        request_id=request_id(),
    )
    return JSONResponse(status_code=400, content=payload.model_dump(mode="json"))


@app.get("/health")
def health() -> dict[str, Any]:
    return ok({"status": "ok"})


@app.post("/api/projects")
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    return ok(service.create_project(payload))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    project = service.get_project(project_id)
    return ok(
        {
            "project": project,
            "quota": store.user_quota,
            "copyright_notice": store.safety_policy.copyright_notice,
        }
    )


@app.post("/api/projects/{project_id}/chapters/generate")
def create_task(project_id: str, payload: TaskCreateRequest) -> dict[str, Any]:
    return ok(service.create_task(project_id, payload))


@app.post("/api/projects/{project_id}/tasks/{task_id}/run")
def run_task(project_id: str, task_id: str) -> dict[str, Any]:
    return ok(service.run_task(project_id, task_id))


@app.get("/api/projects/{project_id}/tasks/{task_id}")
def get_task(project_id: str, task_id: str) -> dict[str, Any]:
    project = service.get_project(project_id)
    task = next(task for task in project.tasks if task.id == task_id)
    chapters = [chapter for chapter in project.chapters if chapter.id in task.chapter_ids]
    return ok({"task": task, "chapters": chapters, "memory": project.memory})


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/confirm")
def confirm_chapter(project_id: str, chapter_id: str) -> dict[str, Any]:
    return ok(service.confirm_chapter(project_id, chapter_id))


@app.get("/api/chapters/{chapter_id}/outline-options")
def get_outline_options(chapter_id: str) -> dict[str, Any]:
    chapter = next(
        chapter
        for project in store.projects.values()
        for chapter in project.chapters
        if chapter.id == chapter_id
    )
    return ok(chapter.outline_options)


@app.get("/api/chapters/{chapter_id}/drafts")
def get_drafts(chapter_id: str) -> dict[str, Any]:
    chapter = next(
        chapter
        for project in store.projects.values()
        for chapter in project.chapters
        if chapter.id == chapter_id
    )
    return ok(
        {
            "drafts": chapter.drafts,
            "final_draft_id": chapter.final_draft_id,
            "needs_manual_review": chapter.needs_manual_review,
            "rewrite_count": chapter.rewrite_count,
        }
    )


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/paragraph-rewrite")
def rewrite_paragraph(project_id: str, chapter_id: str, payload: RewriteRequest) -> dict[str, Any]:
    return ok(service.rewrite_paragraph(project_id, chapter_id, payload))


@app.post("/api/projects/{project_id}/chapters/{chapter_id}/paragraph-expand")
def expand_paragraph(project_id: str, chapter_id: str, payload: RewriteRequest) -> dict[str, Any]:
    return ok(service.expand_paragraph(project_id, chapter_id, payload))


@app.get("/api/templates")
def list_templates() -> dict[str, Any]:
    return ok(service.list_templates())


@app.post("/api/templates")
def create_template(payload: dict[str, Any]) -> dict[str, Any]:
    template = Template(
        id=new_id("template"),
        name=payload["name"],
        genre=payload["genre"],
        style_rules=payload["style_rules"],
        world_template=payload["world_template"],
        character_template=payload["character_template"],
        outline_template=payload["outline_template"],
        status=payload.get("status", "draft"),
        owner_type="user",
    )
    return ok(service.create_template(template))


@app.get("/api/membership/quotas")
def get_quotas() -> dict[str, Any]:
    return ok({"quota": store.user_quota, "plan": list(store.membership_plans.values())[0]})


@app.get("/admin/templates")
def admin_templates() -> dict[str, Any]:
    return ok(service.list_templates())


@app.post("/admin/templates/{template_id}/publish")
def admin_publish_template(template_id: str) -> dict[str, Any]:
    return ok(service.publish_template(template_id))


@app.get("/admin/memberships")
def admin_memberships() -> dict[str, Any]:
    return ok({"plans": list(store.membership_plans.values()), "quota": store.user_quota})


@app.post("/admin/quotas/adjust")
def admin_adjust_quota(payload: QuotaAdjustRequest) -> dict[str, Any]:
    return ok(service.adjust_quota(payload.free_delta, payload.monthly_delta))


@app.get("/admin/orders")
def admin_orders() -> dict[str, Any]:
    return ok(list(store.orders.values()))


@app.get("/admin/safety/policies")
def admin_safety_policies() -> dict[str, Any]:
    return ok(store.safety_policy)


@app.patch("/admin/safety/policies/{policy_id}")
def admin_update_safety_policy(policy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if store.safety_policy.id != policy_id:
        raise DomainError("INVALID_ARGUMENT", "policy not found", {"policy_id": policy_id})
    store.safety_policy.blocked_terms = payload.get("blocked_terms", store.safety_policy.blocked_terms)
    store.safety_policy.copyright_notice = payload.get(
        "copyright_notice",
        store.safety_policy.copyright_notice,
    )
    store.log("safety_policy_updated", {"policy_id": policy_id})
    return ok(store.safety_policy)


@app.get("/admin/logs/tasks")
def admin_task_logs() -> dict[str, Any]:
    return ok(store.audit_logs)
