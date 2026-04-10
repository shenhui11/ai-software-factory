from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


UploadStatus = Literal[
    "uploaded",
    "validating",
    "cleaning",
    "report_generating",
    "completed",
    "failed",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserContext(BaseModel):
    user_id: str
    tenant_id: str
    role: Literal["admin", "analyst", "viewer"]


class FieldIssue(BaseModel):
    field: str
    issue_type: str
    count: int


class DataSummary(BaseModel):
    upload_id: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    field_issues: list[FieldIssue]


class ReportPayload(BaseModel):
    report_id: str
    upload_id: str
    title: str = "Excel Analysis Report"
    generated_at: datetime
    metrics: dict[str, int]
    sections: list[dict[str, object]] = Field(default_factory=list)


class ProcessingJob(BaseModel):
    id: str
    upload_id: str
    tenant_id: str
    status: UploadStatus
    attempt: int
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class UploadRecord(BaseModel):
    id: str
    tenant_id: str
    file_name: str
    file_size_bytes: int
    object_key: str
    status: UploadStatus
    created_by_user_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_error_code: str | None = None
    last_error_message: str | None = None
    summary: DataSummary | None = None
    report_id: str | None = None


class ReportRecord(BaseModel):
    id: str
    upload_id: str
    tenant_id: str
    status: Literal["completed"]
    title: str
    report_payload: ReportPayload
    generated_at: datetime
    allowed_roles: set[str] = Field(default_factory=set)
    allowed_user_ids: set[str] = Field(default_factory=set)


class AuditLog(BaseModel):
    actor_user_id: str
    tenant_id: str
    action: str
    target_id: str
    result: Literal["allowed", "denied", "success", "failed"]
    created_at: datetime = Field(default_factory=utc_now)


class ProcessingLog(BaseModel):
    upload_id: str
    tenant_id: str
    stage: Literal["upload", "validating", "cleaning", "report_generating", "completed", "failed"]
    message: str
    created_at: datetime = Field(default_factory=utc_now)
