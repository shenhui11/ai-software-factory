from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    sort_order: int = 0
    is_active: bool = True


class CategoryPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    is_active: bool = True


class TagPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    is_active: bool | None = None


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    content: str = ""
    category_id: str
    tag_ids: list[str] = Field(default_factory=list)
    status: Literal["draft", "published", "offline"] = "draft"


class TemplatePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    content: str | None = None
    category_id: str | None = None
    tag_ids: list[str] | None = None
    status: Literal["draft", "published", "offline"] | None = None


class UserTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    content: str = Field(min_length=1)
    category_id: str
    tag_ids: list[str] = Field(default_factory=list)
    source_template_id: str | None = None
    ai_generated: bool = False


class UserTemplatePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    content: str | None = None
    category_id: str | None = None
    tag_ids: list[str] | None = None


class DraftGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    context: str | None = None
