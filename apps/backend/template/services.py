from __future__ import annotations

import logging
from dataclasses import asdict

from apps.backend.application.services import DomainError
from apps.backend.domain.models import utc_now
from apps.backend.infrastructure.store import store
from apps.backend.template.models import (
    Actor,
    Template,
    TemplateAuditEvent,
    TemplateCategory,
    TemplateGenerationRecord,
    TemplateTag,
)

logger = logging.getLogger(__name__)

ALLOWED_STATUSES = {"draft", "published", "offline"}


class AiGateway:
    def generate_template_draft(self, prompt: str, context: str) -> dict[str, object]:
        compact_prompt = prompt.strip()
        category_name = "AI 灵感"
        return {
            "name": compact_prompt[:60],
            "description": f"根据需求生成的模板草稿：{compact_prompt}",
            "content": (
                f"目标：{compact_prompt}\n\n"
                f"背景：{context.strip() or '未提供额外上下文'}\n\n"
                "步骤：\n1. 明确目标\n2. 拆解关键约束\n3. 输出可执行结果"
            ),
            "suggested_category_name": category_name,
            "suggested_tags": ["AI生成", "草稿"],
            "model_name": "builtin-template-draft-v1",
        }


ai_gateway = AiGateway()


def _ensure_actor(actor: Actor | None) -> Actor:
    if actor is None:
        raise DomainError(
            "authentication_required",
            "Authentication is required.",
            status_code=401,
        )
    return actor


def _ensure_admin(actor: Actor | None) -> Actor:
    current_actor = _ensure_actor(actor)
    if current_actor.role != "admin":
        raise DomainError(
            "forbidden",
            "Admin permission is required.",
            status_code=403,
        )
    return current_actor


def _get_template(template_id: str) -> Template:
    template = store.templates.get(template_id)
    if template is None:
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    return template


def _get_category(category_id: str) -> TemplateCategory:
    category = store.template_categories.get(category_id)
    if category is None:
        raise DomainError("category_not_found", "Category not found.", status_code=404)
    return category


def _get_tag(tag_id: str) -> TemplateTag:
    tag = store.template_tags.get(tag_id)
    if tag is None:
        raise DomainError("tag_not_found", "Tag not found.", status_code=404)
    return tag


def _validate_status(status: str) -> str:
    if status not in ALLOWED_STATUSES:
        raise DomainError(
            "invalid_template_status",
            "Template status is invalid.",
            details={"status": status},
            status_code=400,
        )
    return status


def _validate_template_payload(
    *,
    name: str,
    content: str,
    category_id: str,
    tag_ids: list[str],
) -> None:
    if not name.strip():
        raise DomainError("invalid_name", "Template name is required.", status_code=400)
    if not content.strip():
        raise DomainError(
            "invalid_content",
            "Template content is required.",
            status_code=400,
        )
    _get_category(category_id)
    seen_tag_ids: set[str] = set()
    for tag_id in tag_ids:
        if tag_id in seen_tag_ids:
            raise DomainError(
                "duplicate_tag",
                "Tag ids must be unique.",
                details={"tag_id": tag_id},
                status_code=400,
            )
        _get_tag(tag_id)
        seen_tag_ids.add(tag_id)


def _record_audit(
    *,
    template_id: str,
    actor: Actor,
    event_type: str,
    event_payload: dict[str, object],
    request_id: str,
) -> None:
    event = TemplateAuditEvent(
        template_id=template_id,
        operator_user_id=actor.user_id,
        operator_role=actor.role,
        event_type=event_type,
        event_payload=event_payload,
        request_id=request_id,
    )
    store.template_audit_events[event.id] = event
    logger.info(
        "template_audit_event",
        extra={
            "template_id": template_id,
            "operator_user_id": actor.user_id,
            "event_type": event_type,
            "request_id": request_id,
        },
    )


def serialize_template(template: Template) -> dict[str, object]:
    payload = asdict(template)
    category = _get_category(template.category_id)
    payload["category"] = asdict(category)
    payload["tags"] = [asdict(_get_tag(tag_id)) for tag_id in template.tag_ids]
    return payload


def list_templates(
    actor: Actor | None,
    *,
    scope: str = "all",
    keyword: str | None = None,
    category_id: str | None = None,
    tag: str | None = None,
) -> dict[str, list[dict[str, object]]]:
    current_actor = _ensure_actor(actor)
    templates: list[Template] = []
    normalized_keyword = (keyword or "").strip().lower()
    for template in store.templates.values():
        if template.template_type == "system":
            if template.status != "published":
                continue
            if scope == "mine":
                continue
        elif template.owner_user_id != current_actor.user_id:
            continue
        elif scope == "system":
            continue
        if category_id and template.category_id != category_id:
            continue
        if tag and tag not in template.tag_ids:
            continue
        if normalized_keyword:
            haystack = f"{template.name} {template.description} {template.content}".lower()
            if normalized_keyword not in haystack:
                continue
        templates.append(template)
    templates.sort(key=lambda item: item.updated_at, reverse=True)
    return {"items": [serialize_template(template) for template in templates]}


def get_template_detail(actor: Actor | None, template_id: str) -> dict[str, object]:
    current_actor = _ensure_actor(actor)
    template = _get_template(template_id)
    if template.template_type == "system":
        if template.status != "published" and current_actor.role != "admin":
            raise DomainError("template_not_found", "Template not found.", status_code=404)
    elif template.owner_user_id != current_actor.user_id:
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    return serialize_template(template)


def use_template(actor: Actor | None, template_id: str) -> dict[str, object]:
    template = get_template_detail(actor, template_id)
    return {
        "template_id": template["id"],
        "template_type": template["template_type"],
        "name": template["name"],
        "description": template["description"],
        "content": template["content"],
        "category_id": template["category_id"],
        "tag_ids": list(template["tag_ids"]),
    }


def create_user_template(
    actor: Actor | None,
    payload: dict[str, object],
) -> dict[str, object]:
    current_actor = _ensure_actor(actor)
    category_id = str(payload["category_id"])
    tag_ids = list(payload.get("tag_ids", []))
    _validate_template_payload(
        name=str(payload["name"]),
        content=str(payload["content"]),
        category_id=category_id,
        tag_ids=tag_ids,
    )
    template = Template(
        template_type="user",
        status="draft",
        name=str(payload["name"]).strip(),
        description=str(payload.get("description", "")).strip(),
        content=str(payload["content"]).strip(),
        category_id=category_id,
        creator_user_id=current_actor.user_id,
        owner_user_id=current_actor.user_id,
        tag_ids=tag_ids,
        source_template_id=payload.get("source_template_id"),
        ai_generated=bool(payload.get("ai_generated", False)),
    )
    store.templates[template.id] = template
    logger.info("user_template_created", extra={"template_id": template.id})
    return serialize_template(template)


def update_user_template(
    actor: Actor | None,
    template_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    current_actor = _ensure_actor(actor)
    template = _get_template(template_id)
    if template.template_type != "user" or template.owner_user_id != current_actor.user_id:
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    next_name = str(payload.get("name", template.name))
    next_content = str(payload.get("content", template.content))
    next_category_id = str(payload.get("category_id", template.category_id))
    next_tag_ids = list(payload.get("tag_ids", template.tag_ids))
    _validate_template_payload(
        name=next_name,
        content=next_content,
        category_id=next_category_id,
        tag_ids=next_tag_ids,
    )
    template.name = next_name.strip()
    template.description = str(payload.get("description", template.description)).strip()
    template.content = next_content.strip()
    template.category_id = next_category_id
    template.tag_ids = next_tag_ids
    template.updated_at = utc_now()
    logger.info("user_template_updated", extra={"template_id": template.id})
    return serialize_template(template)


def delete_user_template(actor: Actor | None, template_id: str) -> None:
    current_actor = _ensure_actor(actor)
    template = _get_template(template_id)
    if template.template_type != "user" or template.owner_user_id != current_actor.user_id:
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    del store.templates[template_id]
    logger.info("user_template_deleted", extra={"template_id": template_id})


def clone_system_template(actor: Actor | None, template_id: str) -> dict[str, object]:
    current_actor = _ensure_actor(actor)
    template = _get_template(template_id)
    if template.template_type != "system" or template.status != "published":
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    payload = {
        "name": f"{template.name} - Copy",
        "description": template.description,
        "content": template.content,
        "category_id": template.category_id,
        "tag_ids": list(template.tag_ids),
        "source_template_id": template.id,
    }
    return create_user_template(current_actor, payload)


def generate_template_draft(
    actor: Actor | None,
    payload: dict[str, str],
) -> dict[str, object]:
    current_actor = _ensure_actor(actor)
    prompt = payload["prompt"].strip()
    context = payload.get("context", "").strip()
    try:
        result = ai_gateway.generate_template_draft(prompt, context)
    except Exception as exc:  # pragma: no cover
        raise DomainError(
            "template_generation_failed",
            "Template generation failed.",
            details={"reason": str(exc)},
            status_code=502,
        ) from exc
    record = TemplateGenerationRecord(
        user_id=current_actor.user_id,
        prompt=prompt,
        request_context=context,
        generated_name=str(result["name"]),
        generated_description=str(result["description"]),
        generated_content=str(result["content"]),
        suggested_category_name=str(result["suggested_category_name"]),
        suggested_tags=list(result["suggested_tags"]),
        model_name=str(result["model_name"]),
        status="success",
    )
    store.template_generation_records[record.id] = record
    return {
        "name": record.generated_name,
        "description": record.generated_description,
        "content": record.generated_content,
        "suggested_category_name": record.suggested_category_name,
        "suggested_tags": record.suggested_tags,
        "generation_note": "Draft generated successfully.",
        "record_id": record.id,
    }


def list_admin_templates(
    actor: Actor | None,
    *,
    status: str | None = None,
    keyword: str | None = None,
    category_id: str | None = None,
    tag_id: str | None = None,
) -> dict[str, list[dict[str, object]]]:
    _ensure_admin(actor)
    items: list[Template] = []
    normalized_keyword = (keyword or "").strip().lower()
    for template in store.templates.values():
        if template.template_type != "system":
            continue
        if status and template.status != status:
            continue
        if category_id and template.category_id != category_id:
            continue
        if tag_id and tag_id not in template.tag_ids:
            continue
        if normalized_keyword:
            haystack = f"{template.name} {template.description} {template.content}".lower()
            if normalized_keyword not in haystack:
                continue
        items.append(template)
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return {"items": [serialize_template(template) for template in items]}


def create_admin_template(
    actor: Actor | None,
    payload: dict[str, object],
    request_id: str,
) -> dict[str, object]:
    current_actor = _ensure_admin(actor)
    status = _validate_status(str(payload.get("status", "draft")))
    category_id = str(payload["category_id"])
    tag_ids = list(payload.get("tag_ids", []))
    _validate_template_payload(
        name=str(payload["name"]),
        content=str(payload["content"]),
        category_id=category_id,
        tag_ids=tag_ids,
    )
    template = Template(
        template_type="system",
        status=status,
        name=str(payload["name"]).strip(),
        description=str(payload.get("description", "")).strip(),
        content=str(payload["content"]).strip(),
        category_id=category_id,
        creator_user_id=current_actor.user_id,
        owner_user_id=None,
        tag_ids=tag_ids,
    )
    store.templates[template.id] = template
    _record_audit(
        template_id=template.id,
        actor=current_actor,
        event_type="template_created",
        event_payload={"status": template.status},
        request_id=request_id,
    )
    return serialize_template(template)


def update_admin_template(
    actor: Actor | None,
    template_id: str,
    payload: dict[str, object],
    request_id: str,
) -> dict[str, object]:
    current_actor = _ensure_admin(actor)
    template = _get_template(template_id)
    if template.template_type != "system":
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    next_name = str(payload.get("name", template.name))
    next_content = str(payload.get("content", template.content))
    next_category_id = str(payload.get("category_id", template.category_id))
    next_tag_ids = list(payload.get("tag_ids", template.tag_ids))
    _validate_template_payload(
        name=next_name,
        content=next_content,
        category_id=next_category_id,
        tag_ids=next_tag_ids,
    )
    template.name = next_name.strip()
    template.description = str(payload.get("description", template.description)).strip()
    template.content = next_content.strip()
    template.category_id = next_category_id
    template.tag_ids = next_tag_ids
    if "status" in payload and payload["status"] is not None:
        template.status = _validate_status(str(payload["status"]))
    template.updated_at = utc_now()
    _record_audit(
        template_id=template.id,
        actor=current_actor,
        event_type="template_updated",
        event_payload={"status": template.status},
        request_id=request_id,
    )
    return serialize_template(template)


def publish_admin_template(actor: Actor | None, template_id: str, request_id: str) -> dict[str, object]:
    current_actor = _ensure_admin(actor)
    template = _get_template(template_id)
    if template.template_type != "system":
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    _validate_template_payload(
        name=template.name,
        content=template.content,
        category_id=template.category_id,
        tag_ids=template.tag_ids,
    )
    template.status = "published"
    template.updated_at = utc_now()
    _record_audit(
        template_id=template.id,
        actor=current_actor,
        event_type="template_published",
        event_payload={"status": template.status},
        request_id=request_id,
    )
    return serialize_template(template)


def offline_admin_template(actor: Actor | None, template_id: str, request_id: str) -> dict[str, object]:
    current_actor = _ensure_admin(actor)
    template = _get_template(template_id)
    if template.template_type != "system":
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    template.status = "offline"
    template.updated_at = utc_now()
    _record_audit(
        template_id=template.id,
        actor=current_actor,
        event_type="template_offlined",
        event_payload={"status": template.status},
        request_id=request_id,
    )
    return serialize_template(template)


def delete_admin_template(actor: Actor | None, template_id: str, request_id: str) -> None:
    current_actor = _ensure_admin(actor)
    template = _get_template(template_id)
    if template.template_type != "system":
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    del store.templates[template_id]
    _record_audit(
        template_id=template_id,
        actor=current_actor,
        event_type="template_deleted",
        event_payload={"status": template.status},
        request_id=request_id,
    )


def list_categories(actor: Actor | None) -> dict[str, list[dict[str, object]]]:
    _ensure_admin(actor)
    items = sorted(store.template_categories.values(), key=lambda item: item.sort_order)
    return {"items": [asdict(item) for item in items]}


def create_category(actor: Actor | None, payload: dict[str, object]) -> dict[str, object]:
    _ensure_admin(actor)
    category = TemplateCategory(
        name=str(payload["name"]).strip(),
        description=str(payload.get("description", "")).strip(),
        sort_order=int(payload.get("sort_order", 0)),
        is_active=bool(payload.get("is_active", True)),
    )
    store.template_categories[category.id] = category
    return asdict(category)


def update_category(actor: Actor | None, category_id: str, payload: dict[str, object]) -> dict[str, object]:
    _ensure_admin(actor)
    category = _get_category(category_id)
    if "name" in payload and payload["name"] is not None:
        category.name = str(payload["name"]).strip()
    if "description" in payload and payload["description"] is not None:
        category.description = str(payload["description"]).strip()
    if "sort_order" in payload and payload["sort_order"] is not None:
        category.sort_order = int(payload["sort_order"])
    if "is_active" in payload and payload["is_active"] is not None:
        category.is_active = bool(payload["is_active"])
    category.updated_at = utc_now()
    return asdict(category)


def delete_category(actor: Actor | None, category_id: str) -> None:
    _ensure_admin(actor)
    _get_category(category_id)
    for template in store.templates.values():
        if template.category_id == category_id:
            raise DomainError(
                "category_in_use",
                "Category is still in use.",
                details={"category_id": category_id},
                status_code=400,
            )
    del store.template_categories[category_id]


def list_tags(actor: Actor | None) -> dict[str, list[dict[str, object]]]:
    _ensure_admin(actor)
    items = sorted(store.template_tags.values(), key=lambda item: item.name.lower())
    return {"items": [asdict(item) for item in items]}


def create_tag(actor: Actor | None, payload: dict[str, object]) -> dict[str, object]:
    _ensure_admin(actor)
    tag = TemplateTag(
        name=str(payload["name"]).strip(),
        description=str(payload.get("description", "")).strip(),
        is_active=bool(payload.get("is_active", True)),
    )
    store.template_tags[tag.id] = tag
    return asdict(tag)


def update_tag(actor: Actor | None, tag_id: str, payload: dict[str, object]) -> dict[str, object]:
    _ensure_admin(actor)
    tag = _get_tag(tag_id)
    if "name" in payload and payload["name"] is not None:
        tag.name = str(payload["name"]).strip()
    if "description" in payload and payload["description"] is not None:
        tag.description = str(payload["description"]).strip()
    if "is_active" in payload and payload["is_active"] is not None:
        tag.is_active = bool(payload["is_active"])
    tag.updated_at = utc_now()
    return asdict(tag)


def delete_tag(actor: Actor | None, tag_id: str) -> None:
    _ensure_admin(actor)
    _get_tag(tag_id)
    for template in store.templates.values():
        if tag_id in template.tag_ids:
            raise DomainError(
                "tag_in_use",
                "Tag is still in use.",
                details={"tag_id": tag_id},
                status_code=400,
            )
    del store.template_tags[tag_id]
