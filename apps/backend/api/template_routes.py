from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Header, Query, Response, status

from apps.backend.application import template_services
from apps.backend.api.template_schemas import (
    CategoryCreateRequest,
    CategoryPatchRequest,
    DraftGenerateRequest,
    TagCreateRequest,
    TagPatchRequest,
    TemplateCreateRequest,
    TemplatePatchRequest,
    UserTemplateCreateRequest,
    UserTemplatePatchRequest,
)

router = APIRouter(prefix="/api/v1")


@router.get("/templates")
async def list_templates(
    scope: str = Query(default="all"),
    keyword: str | None = None,
    category_id: str | None = None,
    tag: str | None = None,
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    items = template_services.list_templates(
        user_id=x_user_id,
        scope=scope,
        keyword=keyword,
        category_id=category_id,
        tag=tag,
    )
    return {"items": items}


@router.get("/templates/{template_id}")
async def get_template_detail(
    template_id: str,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.get_template_detail(
        template_id=template_id,
        user_id=x_user_id,
        user_role=x_user_role,
    )


@router.post("/templates/user")
async def create_user_template(
    payload: UserTemplateCreateRequest,
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.create_user_template(
        payload=payload.model_dump(),
        user_id=x_user_id,
    )


@router.patch("/templates/user/{template_id}")
async def update_user_template(
    template_id: str,
    payload: UserTemplatePatchRequest,
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.update_user_template(
        template_id=template_id,
        payload=payload.model_dump(exclude_none=True),
        user_id=x_user_id,
    )


@router.delete("/templates/user/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_template(
    template_id: str,
    x_user_id: str | None = Header(default=None),
) -> Response:
    template_services.delete_user_template(template_id=template_id, user_id=x_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/templates/{template_id}:clone")
async def clone_template(
    template_id: str,
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.clone_system_template(template_id=template_id, user_id=x_user_id)


@router.post("/templates/drafts:generate")
async def generate_template_draft(
    payload: DraftGenerateRequest,
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.generate_template_draft(
        prompt=payload.prompt,
        context=payload.context,
        user_id=x_user_id,
    )


@router.post("/templates/{template_id}:use")
async def use_template(
    template_id: str,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.use_template(
        template_id=template_id,
        user_id=x_user_id,
        user_role=x_user_role,
    )


@router.get("/admin/templates")
async def list_admin_templates(
    status: str | None = None,
    keyword: str | None = None,
    category_id: str | None = None,
    tag_id: str | None = None,
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return {
        "items": template_services.list_admin_templates(
            user_role=x_user_role,
            status=status,
            category_id=category_id,
            keyword=keyword,
            tag_id=tag_id,
        )
    }


@router.post("/admin/templates")
async def create_system_template(
    payload: TemplateCreateRequest,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.create_system_template(
        payload=payload.model_dump(),
        user_id=x_user_id,
        user_role=x_user_role,
    )


@router.patch("/admin/templates/{template_id}")
async def update_system_template(
    template_id: str,
    payload: TemplatePatchRequest,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.update_system_template(
        template_id=template_id,
        payload=payload.model_dump(exclude_none=True),
        user_id=x_user_id,
        user_role=x_user_role,
    )


@router.post("/admin/templates/{template_id}:publish")
async def publish_system_template(
    template_id: str,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.publish_system_template(
        template_id=template_id,
        user_id=x_user_id,
        user_role=x_user_role,
    )


@router.post("/admin/templates/{template_id}:offline")
async def offline_system_template(
    template_id: str,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return template_services.offline_system_template(
        template_id=template_id,
        user_id=x_user_id,
        user_role=x_user_role,
    )


@router.delete("/admin/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_template(
    template_id: str,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> Response:
    template_services.delete_system_template(
        template_id=template_id,
        user_id=x_user_id,
        user_role=x_user_role,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/template-categories")
async def list_categories(
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return {"items": [asdict(item) for item in template_services.list_categories(user_role=x_user_role)]}


@router.post("/admin/template-categories")
async def create_category(
    payload: CategoryCreateRequest,
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return asdict(
        template_services.create_category(
            name=payload.name,
            description=payload.description,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            user_role=x_user_role,
        )
    )


@router.patch("/admin/template-categories/{category_id}")
async def update_category(
    category_id: str,
    payload: CategoryPatchRequest,
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return asdict(
        template_services.update_category(
            category_id=category_id,
            name=payload.name,
            description=payload.description,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            user_role=x_user_role,
        )
    )


@router.delete("/admin/template-categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: str,
    x_user_role: str | None = Header(default=None),
) -> Response:
    template_services.delete_category(category_id=category_id, user_role=x_user_role)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/template-tags")
async def list_tags(
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return {"items": [asdict(item) for item in template_services.list_tags(user_role=x_user_role)]}


@router.post("/admin/template-tags")
async def create_tag(
    payload: TagCreateRequest,
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return asdict(
        template_services.create_tag(
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            user_role=x_user_role,
        )
    )


@router.patch("/admin/template-tags/{tag_id}")
async def update_tag(
    tag_id: str,
    payload: TagPatchRequest,
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return asdict(
        template_services.update_tag(
            tag_id=tag_id,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            user_role=x_user_role,
        )
    )


@router.delete("/admin/template-tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: str,
    x_user_role: str | None = Header(default=None),
) -> Response:
    template_services.delete_tag(tag_id=tag_id, user_role=x_user_role)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
