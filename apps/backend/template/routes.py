from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request

from apps.backend.template import services
from apps.backend.template.models import Actor
from apps.backend.template.schemas import (
    AdminTemplateCreateRequest,
    AdminTemplatePatchRequest,
    TemplateCategoryCreateRequest,
    TemplateCategoryPatchRequest,
    TemplateDraftGenerateRequest,
    TemplateTagCreateRequest,
    TemplateTagPatchRequest,
    UserTemplateCreateRequest,
    UserTemplatePatchRequest,
)

router = APIRouter(prefix="/api/v1")


def get_actor(
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> Actor | None:
    if x_user_id is None or x_user_role is None:
        return None
    role = "admin" if x_user_role == "admin" else "user"
    return Actor(user_id=x_user_id, role=role)


def get_request_id(request: Request) -> str:
    return request.headers.get("x-request-id", str(uuid4()))


@router.get("/templates")
async def list_templates(
    scope: str = Query(default="all"),
    keyword: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.list_templates(
        actor,
        scope=scope,
        keyword=keyword,
        category_id=category_id,
        tag=tag,
    )


@router.get("/templates/{template_id}")
async def get_template_detail(
    template_id: str,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.get_template_detail(actor, template_id)


@router.post("/templates/user")
async def create_user_template(
    payload: UserTemplateCreateRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.create_user_template(actor, payload.model_dump())


@router.patch("/templates/user/{template_id}")
async def update_user_template(
    template_id: str,
    payload: UserTemplatePatchRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.update_user_template(
        actor,
        template_id,
        payload.model_dump(exclude_none=True),
    )


@router.delete("/templates/user/{template_id}")
async def delete_user_template(
    template_id: str,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, bool]:
    services.delete_user_template(actor, template_id)
    return {"success": True}


@router.post("/templates/{template_id}:clone")
async def clone_system_template(
    template_id: str,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.clone_system_template(actor, template_id)


@router.post("/templates/drafts:generate")
async def generate_template_draft(
    payload: TemplateDraftGenerateRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.generate_template_draft(actor, payload.model_dump())


@router.post("/templates/{template_id}:use")
async def use_template(
    template_id: str,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.use_template(actor, template_id)


@router.get("/admin/templates")
async def list_admin_templates(
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    tag_id: str | None = Query(default=None),
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.list_admin_templates(
        actor,
        status=status,
        keyword=keyword,
        category_id=category_id,
        tag_id=tag_id,
    )


@router.post("/admin/templates")
async def create_admin_template(
    request: Request,
    payload: AdminTemplateCreateRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.create_admin_template(
        actor,
        payload.model_dump(),
        get_request_id(request),
    )


@router.patch("/admin/templates/{template_id}")
async def update_admin_template(
    template_id: str,
    request: Request,
    payload: AdminTemplatePatchRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.update_admin_template(
        actor,
        template_id,
        payload.model_dump(exclude_none=True),
        get_request_id(request),
    )


@router.post("/admin/templates/{template_id}:publish")
async def publish_admin_template(
    template_id: str,
    request: Request,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.publish_admin_template(actor, template_id, get_request_id(request))


@router.post("/admin/templates/{template_id}:offline")
async def offline_admin_template(
    template_id: str,
    request: Request,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.offline_admin_template(actor, template_id, get_request_id(request))


@router.delete("/admin/templates/{template_id}")
async def delete_admin_template(
    template_id: str,
    request: Request,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, bool]:
    services.delete_admin_template(actor, template_id, get_request_id(request))
    return {"success": True}


@router.get("/admin/template-categories")
async def list_categories(
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.list_categories(actor)


@router.post("/admin/template-categories")
async def create_category(
    payload: TemplateCategoryCreateRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.create_category(actor, payload.model_dump())


@router.patch("/admin/template-categories/{category_id}")
async def update_category(
    category_id: str,
    payload: TemplateCategoryPatchRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.update_category(actor, category_id, payload.model_dump(exclude_none=True))


@router.delete("/admin/template-categories/{category_id}")
async def delete_category(
    category_id: str,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, bool]:
    services.delete_category(actor, category_id)
    return {"success": True}


@router.get("/admin/template-tags")
async def list_tags(
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.list_tags(actor)


@router.post("/admin/template-tags")
async def create_tag(
    payload: TemplateTagCreateRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.create_tag(actor, payload.model_dump())


@router.patch("/admin/template-tags/{tag_id}")
async def update_tag(
    tag_id: str,
    payload: TemplateTagPatchRequest,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, object]:
    return services.update_tag(actor, tag_id, payload.model_dump(exclude_none=True))


@router.delete("/admin/template-tags/{tag_id}")
async def delete_tag(
    tag_id: str,
    actor: Actor | None = Depends(get_actor),
) -> dict[str, bool]:
    services.delete_tag(actor, tag_id)
    return {"success": True}
