from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from apps.backend.domain.models import new_id, utc_now

TemplateType = Literal["system", "user"]
TemplateStatus = Literal["draft", "published", "offline"]


@dataclass
class TemplateCategory:
    name: str
    description: str
    sort_order: int = 0
    is_active: bool = True
    id: str = field(default_factory=lambda: new_id("tmpl_cat"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class TemplateTag:
    name: str
    description: str
    is_active: bool = True
    id: str = field(default_factory=lambda: new_id("tmpl_tag"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Template:
    template_type: TemplateType
    status: TemplateStatus
    name: str
    description: str
    content: str
    category_id: str
    creator_user_id: str
    owner_user_id: str | None
    tag_ids: list[str] = field(default_factory=list)
    source_template_id: str | None = None
    ai_generated: bool = False
    id: str = field(default_factory=lambda: new_id("tmpl"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class TemplateGenerationRecord:
    user_id: str
    prompt: str
    request_context: str
    generated_name: str
    generated_description: str
    generated_content: str
    suggested_category_name: str
    suggested_tags: list[str]
    model_name: str
    status: str
    error_message: str | None = None
    id: str = field(default_factory=lambda: new_id("tmpl_gen"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class TemplateAuditEvent:
    template_id: str
    operator_user_id: str
    operator_role: str
    event_type: str
    event_payload: dict[str, object]
    request_id: str
    id: str = field(default_factory=lambda: new_id("tmpl_audit"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Actor:
    user_id: str
    role: Literal["admin", "user"]
