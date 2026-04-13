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
    id: str = field(default_factory=lambda: new_id("tplcat"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class TemplateTag:
    name: str
    description: str
    is_active: bool = True
    id: str = field(default_factory=lambda: new_id("tpltag"))
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
    tag_ids: list[str]
    creator_user_id: str
    owner_user_id: str | None
    source_template_id: str | None = None
    ai_generated: bool = False
    id: str = field(default_factory=lambda: new_id("tpl"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class TemplateGenerationRecord:
    user_id: str
    prompt: str
    request_context: str | None
    generated_name: str
    generated_description: str
    generated_content: str
    model_name: str
    status: str
    error_message: str | None = None
    id: str = field(default_factory=lambda: new_id("tplgen"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class TemplateAuditEvent:
    template_id: str
    operator_user_id: str
    operator_role: str
    event_type: str
    event_payload: dict[str, object]
    request_id: str | None = None
    id: str = field(default_factory=lambda: new_id("audit"))
    created_at: datetime = field(default_factory=utc_now)
