from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from apps.backend.application.services import DomainError
from apps.backend.domain.models import utc_now
from apps.backend.domain.template_models import (
    Template,
    TemplateAuditEvent,
    TemplateCategory,
    TemplateGenerationRecord,
    TemplateTag,
)
from apps.backend.infrastructure.store import store

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 5_000


class AiGateway:
    model_name = "deterministic-template-draft-v1"

    def generate_template_draft(
        self,
        *,
        prompt: str,
        context: str | None,
    ) -> dict[str, Any]:
        cleaned = prompt.strip()
        if not cleaned:
            raise DomainError(
                "invalid_prompt",
                "Prompt must not be empty.",
                details={"field": "prompt"},
                status_code=400,
            )
        name = cleaned[:40]
        return {
            "name": f"{name} 模板",
            "description": f"基于需求生成的模板草稿：{cleaned}",
            "content": (
                f"目标：{cleaned}\n\n"
                f"背景：{context or '未提供额外上下文'}\n\n"
                "要求：\n1. 明确目标\n2. 给出关键步骤\n3. 预留可编辑细节"
            ),
            "suggested_category_name": "AI 灵感",
            "suggested_tags": ["ai-generated", "draft"],
            "generation_notes": "single_round_draft",
        }


ai_gateway = AiGateway()


def _ensure_length(value: str, field_name: str) -> str:
    text = value.strip()
    if not text:
        raise DomainError(
            "validation_error",
            f"{field_name} is required.",
            details={"field": field_name},
            status_code=400,
        )
    if len(text) > MAX_TEXT_LENGTH:
        raise DomainError(
            "validation_error",
            f"{field_name} exceeds max length.",
            details={"field": field_name, "max_length": MAX_TEXT_LENGTH},
            status_code=400,
        )
    return text


def _get_template(template_id: str) -> Template:
    template = store.templates.get(template_id)
    if template is None:
        raise DomainError("template_not_found", "Template not found.", status_code=404)
    return template


def _get_category(category_id: str) -> TemplateCategory:
    category = store.template_categories.get(category_id)
    if category is None:
        raise DomainError("category_not_found", "Category not found.", status_code=404)
    if not category.is_active:
        raise DomainError("invalid_category", "Category is inactive.", status_code=400)
    return category


def _get_tag(tag_id: str) -> TemplateTag:
    tag = store.template_tags.get(tag_id)
    if tag is None:
        raise DomainError("tag_not_found", "Tag not found.", status_code=404)
    if not tag.is_active:
        raise DomainError("invalid_tag", "Tag is inactive.", status_code=400)
    return tag


def _validate_tag_ids(tag_ids: list[str]) -> list[str]:
    unique_ids: list[str] = []
    for tag_id in tag_ids:
        _get_tag(tag_id)
        if tag_id not in unique_ids:
            unique_ids.append(tag_id)
    return unique_ids


def _require_admin(role: str | None) -> None:
    if role != "admin":
        raise DomainError("forbidden", "Admin role required.", status_code=403)


def _require_user(user_id: str | None) -> str:
    if not user_id:
        raise DomainError("unauthorized", "Authentication required.", status_code=401)
    return user_id


def _serialize_template(template: Template) -> dict[str, Any]:
    data = asdict(template)
    data["tags"] = [asdict(store.template_tags[tag_id]) for tag_id in template.tag_ids]
    data["category"] = asdict(store.template_categories[template.category_id])
    return data


def _record_audit(
    *,
    template_id: str,
    operator_user_id: str,
    operator_role: str,
    event_type: str,
    payload: dict[str, object],
) -> None:
    event = TemplateAuditEvent(
        template_id=template_id,
        operator_user_id=operator_user_id,
        operator_role=operator_role,
        event_type=event_type,
        event_payload=payload,
    )
    store.template_audit_events[event.id] = event
    logger.info("template_audit_event", extra={"event_type": event_type, "template_id": template_id})


def create_category(
    *,
    name: str,
    description: str,
    sort_order: int,
    is_active: bool,
    user_role: str | None,
) -> TemplateCategory:
    _require_admin(user_role)
    category = TemplateCategory(
        name=_ensure_length(name, "name"),
        description=description.strip(),
        sort_order=sort_order,
        is_active=is_active,
    )
    store.template_categories[category.id] = category
    return category


def update_category(
    *,
    category_id: str,
    name: str | None,
    description: str | None,
    sort_order: int | None,
    is_active: bool | None,
    user_role: str | None,
) -> TemplateCategory:
    _require_admin(user_role)
    category = _get_category(category_id)
    if name is not None:
        category.name = _ensure_length(name, "name")
    if description is not None:
        category.description = description.strip()
    if sort_order is not None:
        category.sort_order = sort_order
    if is_active is not None:
        category.is_active = is_active
    category.updated_at = utc_now()
    return category


def delete_category(*, category_id: str, user_role: str | None) -> None:
    _require_admin(user_role)
    _get_category(category_id)
    del store.template_categories[category_id]


def list_categories(*, user_role: str | None) -> list[TemplateCategory]:
    _require_admin(user_role)
    return sorted(store.template_categories.values(), key=lambda item: (item.sort_order, item.name))


def create_tag(
    *,
    name: str,
    description: str,
    is_active: bool,
    user_role: str | None,
) -> TemplateTag:
    _require_admin(user_role)
    tag = TemplateTag(
        name=_ensure_length(name, "name"),
        description=description.strip(),
        is_active=is_active,
    )
    store.template_tags[tag.id] = tag
    return tag


def update_tag(
    *,
    tag_id: str,
    name: str | None,
    description: str | None,
    is_active: bool | None,
    user_role: str | None,
) -> TemplateTag:
    _require_admin(user_role)
    tag = _get_tag(tag_id)
    if name is not None:
        tag.name = _ensure_length(name, "name")
    if description is not None:
        tag.description = description.strip()
    if is_active is not None:
        tag.is_active = is_active
    tag.updated_at = utc_now()
    return tag


def delete_tag(*, tag_id: str, user_role: str | None) -> None:
    _require_admin(user_role)
    _get_tag(tag_id)
    del store.template_tags[tag_id]


def list_tags(*, user_role: str | None) -> list[TemplateTag]:
    _require_admin(user_role)
    return sorted(store.template_tags.values(), key=lambda item: item.name)


def create_system_template(
    *,
    payload: dict[str, Any],
    user_id: str | None,
    user_role: str | None,
) -> dict[str, Any]:
    _require_admin(user_role)
    operator_id = _require_user(user_id)
    _get_category(payload["category_id"])
    tag_ids = _validate_tag_ids(list(payload.get("tag_ids", [])))
    template = Template(
        template_type="system",
        status=payload.get("status", "draft"),
        name=_ensure_length(payload["name"], "name"),
        description=payload.get("description", "").strip(),
        content=str(payload.get("content", "")),
        category_id=payload["category_id"],
        tag_ids=tag_ids,
        creator_user_id=operator_id,
        owner_user_id=None,
    )
    store.templates[template.id] = template
    _record_audit(
        template_id=template.id,
        operator_user_id=operator_id,
        operator_role="admin",
        event_type="system_template_created",
        payload={"status": template.status},
    )
    return _serialize_template(template)


def update_system_template(
    *,
    template_id: str,
    payload: dict[str, Any],
    user_id: str | None,
    user_role: str | None,
) -> dict[str, Any]:
    _require_admin(user_role)
    operator_id = _require_user(user_id)
    template = _get_template(template_id)
    if template.template_type != "system":
        raise DomainError("invalid_template_type", "Template is not a system template.", status_code=400)
    if "category_id" in payload:
        _get_category(payload["category_id"])
        template.category_id = payload["category_id"]
    if "tag_ids" in payload:
        template.tag_ids = _validate_tag_ids(list(payload["tag_ids"]))
    if "name" in payload:
        template.name = _ensure_length(payload["name"], "name")
    if "description" in payload:
        template.description = str(payload["description"]).strip()
    if "content" in payload:
        template.content = str(payload["content"])
    if "status" in payload:
        template.status = payload["status"]
    template.updated_at = utc_now()
    _record_audit(
        template_id=template.id,
        operator_user_id=operator_id,
        operator_role="admin",
        event_type="system_template_updated",
        payload={"status": template.status},
    )
    return _serialize_template(template)


def _validate_publishable(template: Template) -> None:
    _ensure_length(template.name, "name")
    _ensure_length(template.content, "content")
    _get_category(template.category_id)


def publish_system_template(
    *,
    template_id: str,
    user_id: str | None,
    user_role: str | None,
) -> dict[str, Any]:
    _require_admin(user_role)
    operator_id = _require_user(user_id)
    template = _get_template(template_id)
    if template.template_type != "system":
        raise DomainError("invalid_template_type", "Template is not a system template.", status_code=400)
    _validate_publishable(template)
    template.status = "published"
    template.updated_at = utc_now()
    _record_audit(
        template_id=template.id,
        operator_user_id=operator_id,
        operator_role="admin",
        event_type="system_template_published",
        payload={},
    )
    return _serialize_template(template)


def offline_system_template(
    *,
    template_id: str,
    user_id: str | None,
    user_role: str | None,
) -> dict[str, Any]:
    _require_admin(user_role)
    operator_id = _require_user(user_id)
    template = _get_template(template_id)
    if template.template_type != "system":
        raise DomainError("invalid_template_type", "Template is not a system template.", status_code=400)
    template.status = "offline"
    template.updated_at = utc_now()
    _record_audit(
        template_id=template.id,
        operator_user_id=operator_id,
        operator_role="admin",
        event_type="system_template_offline",
        payload={},
    )
    return _serialize_template(template)


def delete_system_template(
    *,
    template_id: str,
    user_id: str | None,
    user_role: str | None,
) -> None:
    _require_admin(user_role)
    operator_id = _require_user(user_id)
    template = _get_template(template_id)
    if template.template_type != "system":
        raise DomainError("invalid_template_type", "Template is not a system template.", status_code=400)
    del store.templates[template.id]
    _record_audit(
        template_id=template_id,
        operator_user_id=operator_id,
        operator_role="admin",
        event_type="system_template_deleted",
        payload={},
    )


def list_admin_templates(
    *,
    user_role: str | None,
    status: str | None,
    category_id: str | None,
    keyword: str | None,
    tag_id: str | None,
) -> list[dict[str, Any]]:
    _require_admin(user_role)
    items = [item for item in store.templates.values() if item.template_type == "system"]
    if status:
        items = [item for item in items if item.status == status]
    if category_id:
        items = [item for item in items if item.category_id == category_id]
    if keyword:
        lowered = keyword.lower()
        items = [item for item in items if lowered in item.name.lower() or lowered in item.description.lower()]
    if tag_id:
        items = [item for item in items if tag_id in item.tag_ids]
    return [_serialize_template(item) for item in sorted(items, key=lambda item: item.updated_at, reverse=True)]


def create_user_template(
    *,
    payload: dict[str, Any],
    user_id: str | None,
) -> dict[str, Any]:
    owner_id = _require_user(user_id)
    _get_category(payload["category_id"])
    tag_ids = _validate_tag_ids(list(payload.get("tag_ids", [])))
    template = Template(
        template_type="user",
        status="draft",
        name=_ensure_length(payload["name"], "name"),
        description=payload.get("description", "").strip(),
        content=_ensure_length(payload["content"], "content"),
        category_id=payload["category_id"],
        tag_ids=tag_ids,
        creator_user_id=owner_id,
        owner_user_id=owner_id,
        source_template_id=payload.get("source_template_id"),
        ai_generated=bool(payload.get("ai_generated", False)),
    )
    store.templates[template.id] = template
    logger.info("user_template_created", extra={"template_id": template.id, "user_id": owner_id})
    return _serialize_template(template)


def update_user_template(
    *,
    template_id: str,
    payload: dict[str, Any],
    user_id: str | None,
) -> dict[str, Any]:
    owner_id = _require_user(user_id)
    template = _get_template(template_id)
    if template.template_type != "user":
        raise DomainError("forbidden", "System templates cannot be edited here.", status_code=403)
    if template.owner_user_id != owner_id:
        raise DomainError("forbidden", "Template access denied.", status_code=403)
    if "category_id" in payload:
        _get_category(payload["category_id"])
        template.category_id = payload["category_id"]
    if "tag_ids" in payload:
        template.tag_ids = _validate_tag_ids(list(payload["tag_ids"]))
    if "name" in payload:
        template.name = _ensure_length(payload["name"], "name")
    if "description" in payload:
        template.description = str(payload["description"]).strip()
    if "content" in payload:
        template.content = _ensure_length(payload["content"], "content")
    template.updated_at = utc_now()
    return _serialize_template(template)


def delete_user_template(*, template_id: str, user_id: str | None) -> None:
    owner_id = _require_user(user_id)
    template = _get_template(template_id)
    if template.template_type != "user" or template.owner_user_id != owner_id:
        raise DomainError("forbidden", "Template access denied.", status_code=403)
    del store.templates[template_id]


def list_templates(
    *,
    user_id: str | None,
    scope: str,
    keyword: str | None,
    category_id: str | None,
    tag: str | None,
) -> list[dict[str, Any]]:
    current_user_id = _require_user(user_id)
    items = list(store.templates.values())
    visible: list[Template] = []
    for item in items:
        if item.template_type == "system" and item.status == "published":
            visible.append(item)
        if item.template_type == "user" and item.owner_user_id == current_user_id:
            visible.append(item)
    if scope == "system":
        visible = [item for item in visible if item.template_type == "system"]
    elif scope == "mine":
        visible = [item for item in visible if item.template_type == "user"]
    if keyword:
        lowered = keyword.lower()
        visible = [item for item in visible if lowered in item.name.lower() or lowered in item.description.lower()]
    if category_id:
        visible = [item for item in visible if item.category_id == category_id]
    if tag:
        visible = [item for item in visible if tag in item.tag_ids]
    return [_serialize_template(item) for item in sorted(visible, key=lambda item: item.updated_at, reverse=True)]


def get_template_detail(
    *,
    template_id: str,
    user_id: str | None,
    user_role: str | None,
) -> dict[str, Any]:
    current_user_id = _require_user(user_id)
    template = _get_template(template_id)
    if template.template_type == "system":
        if template.status != "published" and user_role != "admin":
            raise DomainError("forbidden", "Template access denied.", status_code=403)
    elif template.owner_user_id != current_user_id:
        raise DomainError("forbidden", "Template access denied.", status_code=403)
    return _serialize_template(template)


def clone_system_template(
    *,
    template_id: str,
    user_id: str | None,
) -> dict[str, Any]:
    owner_id = _require_user(user_id)
    source = _get_template(template_id)
    if source.template_type != "system" or source.status != "published":
        raise DomainError("forbidden", "Only published system templates can be cloned.", status_code=403)
    clone = Template(
        template_type="user",
        status="draft",
        name=source.name,
        description=source.description,
        content=source.content,
        category_id=source.category_id,
        tag_ids=list(source.tag_ids),
        creator_user_id=owner_id,
        owner_user_id=owner_id,
        source_template_id=source.id,
    )
    store.templates[clone.id] = clone
    logger.info("template_cloned", extra={"source_template_id": source.id, "template_id": clone.id})
    return _serialize_template(clone)


def use_template(
    *,
    template_id: str,
    user_id: str | None,
    user_role: str | None,
) -> dict[str, Any]:
    template = get_template_detail(template_id=template_id, user_id=user_id, user_role=user_role)
    return {
        "template_id": template["id"],
        "template_type": template["template_type"],
        "name": template["name"],
        "description": template["description"],
        "content": template["content"],
        "category_id": template["category_id"],
        "tag_ids": template["tag_ids"],
    }


def generate_template_draft(
    *,
    prompt: str,
    context: str | None,
    user_id: str | None,
) -> dict[str, Any]:
    current_user_id = _require_user(user_id)
    draft = ai_gateway.generate_template_draft(prompt=prompt, context=context)
    record = TemplateGenerationRecord(
        user_id=current_user_id,
        prompt=prompt,
        request_context=context,
        generated_name=draft["name"],
        generated_description=draft["description"],
        generated_content=draft["content"],
        model_name=ai_gateway.model_name,
        status="success",
    )
    store.template_generation_records[record.id] = record
    return {
        **draft,
        "record_id": record.id,
    }
