from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from apps.backend.api.schemas import (
    CanonRequest,
    ChapterCreateRequest,
    ChapterDraftRequest,
    ChapterPatchRequest,
    IssueFixRequest,
    ParagraphEditRequest,
    ProjectCreateRequest,
    ProjectPatchRequest,
    SnapshotRequest,
)
from apps.backend.application import services

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/projects")
async def create_project(payload: ProjectCreateRequest) -> dict[str, object]:
    project = services.create_project(payload.model_dump())
    return asdict(project)


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, object]:
    project = services.get_project(project_id)
    return asdict(project)


@router.patch("/projects/{project_id}")
async def patch_project(project_id: str, payload: ProjectPatchRequest) -> dict[str, object]:
    project = services.update_project(
        project_id,
        payload.model_dump(exclude_none=True),
    )
    return asdict(project)


@router.get("/projects/{project_id}/canon")
async def get_canon(project_id: str) -> dict[str, object]:
    return asdict(services.get_or_update_canon(project_id))


@router.put("/projects/{project_id}/canon")
async def put_canon(project_id: str, payload: CanonRequest) -> dict[str, object]:
    canon = services.get_or_update_canon(project_id, payload.model_dump())
    return asdict(canon)


@router.post("/projects/{project_id}/outline:generate")
async def generate_outline(project_id: str) -> dict[str, object]:
    outline = services.generate_outline(project_id)
    return asdict(outline)


@router.get("/projects/{project_id}/outline")
async def get_outline(project_id: str) -> dict[str, object]:
    return asdict(services.get_outline(project_id))


@router.post("/projects/{project_id}/chapters")
async def create_chapter(project_id: str, payload: ChapterCreateRequest) -> dict[str, object]:
    chapter = services.create_chapter(project_id, payload.model_dump())
    return asdict(chapter)


@router.post("/chapters/{chapter_id}/draft:generate")
async def generate_chapter_draft(
    chapter_id: str,
    payload: ChapterDraftRequest,
) -> dict[str, object]:
    version = services.generate_chapter_draft(chapter_id, payload.model_dump())
    return asdict(version)


@router.get("/chapters/{chapter_id}")
async def get_chapter(chapter_id: str) -> dict[str, object]:
    details = services.get_chapter(chapter_id)
    return {
        "chapter": asdict(details["chapter"]),
        "content": details["content"],
        "current_version": (
            asdict(details["current_version"])
            if details["current_version"] is not None
            else None
        ),
    }


@router.patch("/chapters/{chapter_id}")
async def patch_chapter(chapter_id: str, payload: ChapterPatchRequest) -> dict[str, object]:
    version = services.save_chapter(chapter_id, payload.content)
    return asdict(version)


@router.post("/chapters/{chapter_id}/edits")
async def create_edit(chapter_id: str, payload: ParagraphEditRequest) -> dict[str, object]:
    suggestion = services.create_paragraph_edit(chapter_id, payload.model_dump())
    return {
        "candidates": [asdict(suggestion)],
    }


@router.post("/chapters/{chapter_id}/qa-scans")
async def create_qa_scan(chapter_id: str) -> dict[str, object]:
    scan = services.create_qa_scan(chapter_id)
    return asdict(scan)


@router.get("/chapters/{chapter_id}/qa-scans/{scan_id}")
async def get_qa_scan(chapter_id: str, scan_id: str) -> dict[str, object]:
    return asdict(services.get_qa_scan(chapter_id, scan_id))


@router.post("/qa-issues/{issue_id}/fix")
async def create_issue_fix(issue_id: str, payload: IssueFixRequest) -> dict[str, object]:
    result = services.create_issue_fix(
        issue_id=issue_id,
        allowed_range=payload.allowed_range.model_dump(),
        strategy=payload.strategy,
    )
    return {
        "version": asdict(result["version"]),
        "affected_range": result["affected_range"],
    }


@router.get("/chapters/{chapter_id}/versions")
async def get_versions(chapter_id: str) -> dict[str, object]:
    versions = [asdict(version) for version in services.list_versions(chapter_id)]
    return {"items": versions}


@router.post("/chapters/{chapter_id}/versions")
async def create_snapshot(chapter_id: str, payload: SnapshotRequest) -> dict[str, object]:
    version = services.create_snapshot(chapter_id, payload.version_note)
    return asdict(version)


@router.get("/versions/{version_id}/diff")
async def get_version_diff(
    version_id: str,
    base_version_id: str = Query(...),
) -> dict[str, object]:
    return services.get_diff(version_id, base_version_id)


@router.post("/versions/{version_id}:restore")
async def restore_version(version_id: str) -> dict[str, object]:
    version = services.restore_version(version_id)
    return asdict(version)


@router.get("/projects/{project_id}/export")
async def export_project(project_id: str, format: str = Query(...)) -> dict[str, str]:
    return services.export_project(project_id, format)
