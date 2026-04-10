from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from packages.excel_reports.auth import get_current_user, require_role
from packages.excel_reports.models import UserContext
from packages.excel_reports.service import (
    create_upload,
    get_report_for_actor,
    get_upload_for_actor,
    record_audit,
    retry_upload,
)
from packages.excel_reports.store import get_store

router = APIRouter()


@router.post("/uploads")
async def post_upload(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
):
    store = get_store()
    try:
        require_role(user, "admin")
    except HTTPException:
        record_audit(store, user, "upload.create", file.filename or "-", "denied")
        raise
    content = await file.read()
    upload, job = create_upload(store, user, file.filename or "", file.content_type or "", content)
    record_audit(store, user, "upload.create", upload.id, "success")
    return {
        "upload_id": upload.id,
        "job_id": job.id,
        "status": "uploaded",
        "created_at": upload.created_at,
    }


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str, user: UserContext = Depends(get_current_user)):
    store = get_store()
    try:
        upload = get_upload_for_actor(store, upload_id, user)
    except HTTPException:
        record_audit(store, user, "upload.read", upload_id, "denied")
        raise
    record_audit(store, user, "upload.read", upload.id, "allowed")
    return {
        "upload_id": upload.id,
        "status": upload.status,
        "error_code": upload.last_error_code,
        "error_message": upload.last_error_message,
        "summary_ready": upload.summary is not None,
        "report_ready": upload.report_id is not None,
        "report_id": upload.report_id,
        "updated_at": upload.updated_at,
    }


@router.post("/uploads/{upload_id}/retry")
def post_retry(upload_id: str, user: UserContext = Depends(get_current_user)):
    store = get_store()
    try:
        require_role(user, "admin")
        upload = get_upload_for_actor(store, upload_id, user)
    except HTTPException:
        record_audit(store, user, "upload.retry", upload_id, "denied")
        raise
    job = retry_upload(store, user, upload)
    record_audit(store, user, "upload.retry", upload.id, "success")
    return {"upload_id": upload.id, "job_id": job.id, "status": "uploaded"}


@router.get("/uploads/{upload_id}/summary")
def get_summary(upload_id: str, user: UserContext = Depends(get_current_user)):
    store = get_store()
    try:
        require_role(user, "admin", "analyst")
        upload = get_upload_for_actor(store, upload_id, user)
    except HTTPException:
        record_audit(store, user, "summary.read", upload_id, "denied")
        raise
    if upload.summary is None:
        record_audit(store, user, "summary.read", upload.id, "denied")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "summary_not_ready", "message": "Summary is available only after successful processing."},
        )
    record_audit(store, user, "summary.read", upload.id, "allowed")
    return upload.summary.model_dump(mode="json")


@router.get("/reports/{report_id}")
def get_report(report_id: str, user: UserContext = Depends(get_current_user)):
    store = get_store()
    try:
        report = get_report_for_actor(store, report_id, user)
    except HTTPException:
        record_audit(store, user, "report.read", report_id, "denied")
        raise
    record_audit(store, user, "report.read", report.id, "allowed")
    return report.report_payload.model_dump(mode="json")
