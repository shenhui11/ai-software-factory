from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    sort_order: int = 0
    is_active: bool = True


class TemplateCategoryPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None
    is_active: bool | None = None


class TemplateTagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    is_active: bool = True


class TemplateTagPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    content: str = Field(min_length=1, max_length=10000)
    category_id: str = Field(min_length=1)
    tag_ids: list[str] = Field(default_factory=list, max_length=20)


class UserTemplateCreateRequest(TemplateCreateRequest):
    pass


class UserTemplatePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    category_id: str | None = Field(default=None, min_length=1)
    tag_ids: list[str] | None = Field(default=None, max_length=20)


class AdminTemplateCreateRequest(TemplateCreateRequest):
    status: str = Field(default="draft")


class AdminTemplatePatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    category_id: str | None = Field(default=None, min_length=1)
    tag_ids: list[str] | None = Field(default=None, max_length=20)
    status: str | None = None


class TemplateDraftGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    context: str = Field(default="", max_length=2000)
