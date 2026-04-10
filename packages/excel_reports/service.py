from __future__ import annotations

from collections import Counter
import io
import zipfile
from xml.etree import ElementTree

from fastapi import HTTPException, status

from packages.excel_reports.models import (
    AuditLog,
    DataSummary,
    FieldIssue,
    ProcessingJob,
    ProcessingLog,
    ReportPayload,
    ReportRecord,
    UploadRecord,
    UserContext,
    utc_now,
)
from packages.excel_reports.store import InMemoryStore

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
ALLOWED_COLUMNS = ("customer_id", "customer_name", "amount")
REQUIRED_FIELDS = ("customer_id", "amount")
SPREADSHEET_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class ValidationFailure(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def record_audit(store: InMemoryStore, actor: UserContext, action: str, target_id: str, result: str) -> None:
    store.audit_logs.append(
        AuditLog(
            actor_user_id=actor.user_id,
            tenant_id=actor.tenant_id,
            action=action,
            target_id=target_id,
            result=result,
        )
    )


def record_processing_log(store: InMemoryStore, upload: UploadRecord, stage: str, message: str) -> None:
    store.processing_logs.append(
        ProcessingLog(
            upload_id=upload.id,
            tenant_id=upload.tenant_id,
            stage=stage,
            message=message,
        )
    )


def ensure_same_tenant(actor: UserContext, tenant_id: str) -> None:
    if actor.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Cross-tenant access is denied."},
        )


def can_retry(status_value: str) -> bool:
    return status_value == "failed"


def validate_headers(headers: list[str]) -> None:
    invalid_columns = [header for header in headers if header not in ALLOWED_COLUMNS]
    if invalid_columns:
        raise ValidationFailure(
            "invalid_columns",
            f"Structural validation failed. Invalid columns: {', '.join(invalid_columns)}.",
            {"columns": invalid_columns, "error_category": "structural"},
        )
    missing_columns = [header for header in ALLOWED_COLUMNS if header not in headers]
    if missing_columns:
        raise ValidationFailure(
            "missing_columns",
            f"Structural validation failed. Missing columns: {', '.join(missing_columns)}.",
            {"columns": missing_columns, "error_category": "structural"},
        )


def validate_required_fields(row: dict[str, str], row_number: int) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    for field_name in REQUIRED_FIELDS:
        value = str(row.get(field_name, "")).strip()
        if value == "":
            issues.append(
                (
                    field_name,
                    "required_empty",
                    f"Content validation failed. Row {row_number} has empty required field: {field_name}.",
                )
            )
    return issues


def build_summary(upload_id: str, rows: list[dict[str, str]], issues: list[tuple[str, str, str]]) -> DataSummary:
    issue_counter = Counter((field_name, issue_type) for field_name, issue_type, _ in issues)
    field_issues = [
        FieldIssue(field=field_name, issue_type=issue_type, count=count)
        for (field_name, issue_type), count in sorted(issue_counter.items())
    ]
    invalid_rows = len({message.split("Row ", 1)[1].split(" ", 1)[0] for _, _, message in issues})
    return DataSummary(
        upload_id=upload_id,
        total_rows=len(rows),
        valid_rows=len(rows) - invalid_rows,
        invalid_rows=invalid_rows,
        field_issues=field_issues,
    )


def map_validation_error(exc: ValidationFailure) -> dict[str, object]:
    details = dict(exc.details)
    if exc.code in {"invalid_columns", "missing_columns"}:
        details.setdefault("error_category", "structural")
    else:
        details.setdefault("error_category", "content")
    return {
        "code": exc.code,
        "message": exc.message,
        "details": details,
    }


def parse_xlsx_rows(content: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_bytes = archive.read("xl/worksheets/sheet1.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValidationFailure(
            "invalid_xlsx",
            "Structural validation failed. The xlsx file could not be read.",
            {"error_category": "structural"},
        ) from exc

    root = ElementTree.fromstring(xml_bytes)
    parsed_rows: list[list[str]] = []
    for row_element in root.findall(".//x:row", SPREADSHEET_NS):
        row_values: list[str] = []
        for cell in row_element.findall("x:c", SPREADSHEET_NS):
            inline_text = cell.find("x:is/x:t", SPREADSHEET_NS)
            value = inline_text.text if inline_text is not None else cell.findtext("x:v", default="", namespaces=SPREADSHEET_NS)
            row_values.append(value or "")
        parsed_rows.append(row_values)
    if not parsed_rows:
        raise ValidationFailure(
            "missing_columns",
            "Structural validation failed. Missing columns: customer_id, customer_name, amount.",
            {"columns": list(ALLOWED_COLUMNS), "error_category": "structural"},
        )
    return parsed_rows


def normalize_rows(headers: list[str], raw_rows: list[list[str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in raw_rows:
        values = row + [""] * (len(headers) - len(row))
        normalized.append({header: str(values[index]).strip() for index, header in enumerate(headers)})
    return normalized


def process_upload(store: InMemoryStore, upload: UploadRecord, job: ProcessingJob) -> None:
    record_processing_log(store, upload, "upload", "Upload accepted and queued for processing.")
    upload.status = "validating"
    upload.updated_at = utc_now()
    job.status = "validating"
    record_processing_log(store, upload, "validating", "Workbook validation started.")
    try:
        rows = parse_xlsx_rows(store.objects[upload.object_key])
        headers = rows[0]
        validate_headers(headers)
        upload.status = "cleaning"
        job.status = "cleaning"
        record_processing_log(store, upload, "cleaning", "Data cleaning started.")
        normalized_rows = normalize_rows(headers, rows[1:])
        issues: list[tuple[str, str, str]] = []
        for row_number, row in enumerate(normalized_rows, start=2):
            issues.extend(validate_required_fields(row, row_number))
        if issues:
            first_field, issue_type, first_message = issues[0]
            raise ValidationFailure(
                issue_type,
                first_message,
                {"field": first_field, "error_category": "content"},
            )
        upload.status = "report_generating"
        job.status = "report_generating"
        record_processing_log(store, upload, "report_generating", "Report generation started.")
        summary = build_summary(upload.id, normalized_rows, issues)
        report_id = store.next_report_id()
        report_payload = ReportPayload(
            report_id=report_id,
            upload_id=upload.id,
            generated_at=utc_now(),
            metrics={
                "total_rows": summary.total_rows,
                "valid_rows": summary.valid_rows,
                "invalid_rows": summary.invalid_rows,
            },
            sections=[
                {
                    "key": "quality_overview",
                    "title": "数据质量概览",
                    "items": [
                        {"label": "关键字段缺失", "value": sum(issue.count for issue in summary.field_issues if issue.issue_type == "required_empty")},
                        {"label": "无效行数", "value": summary.invalid_rows},
                    ],
                }
            ],
        )
        report = ReportRecord(
            id=report_id,
            upload_id=upload.id,
            tenant_id=upload.tenant_id,
            status="completed",
            title=report_payload.title,
            report_payload=report_payload,
            generated_at=report_payload.generated_at,
        )
        store.reports[report_id] = report
        upload.summary = summary
        upload.report_id = report_id
        upload.status = "completed"
        upload.last_error_code = None
        upload.last_error_message = None
        job.status = "completed"
        job.finished_at = utc_now()
        record_processing_log(store, upload, "completed", "Processing completed successfully.")
    except ValidationFailure as exc:
        error = map_validation_error(exc)
        upload.status = "failed"
        upload.last_error_code = str(error["code"])
        upload.last_error_message = str(error["message"])
        upload.summary = None
        upload.report_id = None
        job.status = "failed"
        job.error_code = str(error["code"])
        job.error_message = str(error["message"])
        job.finished_at = utc_now()
        record_processing_log(store, upload, "failed", str(error["message"]))
    finally:
        upload.updated_at = utc_now()


def create_upload(store: InMemoryStore, actor: UserContext, file_name: str, content_type: str, content: bytes) -> tuple[UploadRecord, ProcessingJob]:
    if not file_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "missing_file", "message": "A file upload is required."},
        )
    if not file_name.lower().endswith(".xlsx") or content_type != XLSX_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "unsupported_file_type", "message": "Only xlsx uploads are supported."},
        )
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "file_too_large", "message": "The uploaded file exceeds the 50 MB limit."},
        )

    upload_id = store.next_upload_id()
    job_id = store.next_job_id()
    object_key = f"uploads/{upload_id}/{file_name}"
    upload = UploadRecord(
        id=upload_id,
        tenant_id=actor.tenant_id,
        file_name=file_name,
        file_size_bytes=len(content),
        object_key=object_key,
        status="uploaded",
        created_by_user_id=actor.user_id,
    )
    job = ProcessingJob(
        id=job_id,
        upload_id=upload_id,
        tenant_id=actor.tenant_id,
        status="uploaded",
        attempt=1,
    )
    store.uploads[upload_id] = upload
    store.jobs[job_id] = job
    store.objects[object_key] = content
    process_upload(store, upload, job)
    return upload, job


def retry_upload(store: InMemoryStore, actor: UserContext, upload: UploadRecord) -> ProcessingJob:
    if not can_retry(upload.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_retry_state", "message": "Retry is allowed only for failed uploads."},
        )
    attempt = sum(1 for job in store.jobs.values() if job.upload_id == upload.id) + 1
    job = ProcessingJob(
        id=store.next_job_id(),
        upload_id=upload.id,
        tenant_id=upload.tenant_id,
        status="uploaded",
        attempt=attempt,
    )
    store.jobs[job.id] = job
    process_upload(store, upload, job)
    return job


def get_upload_for_actor(store: InMemoryStore, upload_id: str, actor: UserContext) -> UploadRecord:
    upload = store.uploads.get(upload_id)
    if upload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "upload_not_found", "message": "Upload not found."})
    ensure_same_tenant(actor, upload.tenant_id)
    return upload


def get_report_for_actor(store: InMemoryStore, report_id: str, actor: UserContext) -> ReportRecord:
    report = store.reports.get(report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "report_not_found", "message": "Report not found."})
    ensure_same_tenant(actor, report.tenant_id)
    if actor.role in report.allowed_roles or actor.user_id in report.allowed_user_ids:
        return report
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "forbidden", "message": "Report access is not authorized."},
    )
