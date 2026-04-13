from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from apps.backend.api.member_schemas import (
    UpdateBenefitsRequest,
    UpdateLevelsRequest,
    UpdateTasksRequest,
)
from apps.backend.application import member_services

router = APIRouter(prefix="/api/v1")


def _request_context(
    x_user_id: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
) -> tuple[str, str, str | None]:
    user_id, role = member_services.get_actor_context(x_user_id, x_role)
    return user_id, role, x_request_id


@router.get("/members/me")
async def get_member_me(
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, _, _ = ctx
    return member_services.get_member_summary(user_id)


@router.get("/members/me/dashboard")
async def get_member_dashboard(
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, _, _ = ctx
    return member_services.get_dashboard(user_id)


@router.get("/members/me/tasks")
async def get_member_tasks(
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, _, _ = ctx
    return {"items": member_services.list_visible_tasks(user_id)}


@router.post("/members/me/check-ins")
async def post_check_in(
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, _, request_id = ctx
    return member_services.perform_check_in(user_id, user_id, request_id)


@router.post("/members/me/tasks/{task_code}/complete")
async def post_task_complete(
    task_code: str,
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, _, request_id = ctx
    return member_services.complete_task(user_id, task_code, user_id, request_id)


@router.get("/members/me/points/ledger")
async def get_points_ledger(
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
    change_type: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20),
) -> dict[str, object]:
    user_id, _, _ = ctx
    return member_services.get_ledger(user_id, change_type, limit, cursor)


@router.get("/members/me/rewards")
async def get_member_rewards(
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, _, _ = ctx
    return member_services.get_rewards(user_id)


@router.get("/admin/member-config")
async def get_member_config(
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, role, _ = ctx
    member_services.require_admin(role)
    return member_services.get_admin_config()


@router.put("/admin/member-config/tasks")
async def put_member_tasks(
    payload: UpdateTasksRequest,
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, role, _ = ctx
    member_services.require_admin(role)
    return member_services.update_task_config(
        [item.model_dump() for item in payload.tasks],
        user_id,
    )


@router.put("/admin/member-config/levels")
async def put_member_levels(
    payload: UpdateLevelsRequest,
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, role, _ = ctx
    member_services.require_admin(role)
    return member_services.update_level_config(
        [item.model_dump() for item in payload.levels],
        user_id,
    )


@router.put("/admin/member-config/benefits")
async def put_member_benefits(
    payload: UpdateBenefitsRequest,
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, role, _ = ctx
    member_services.require_admin(role)
    return member_services.update_benefit_config(payload.model_dump(), user_id)


@router.post("/admin/member-config:publish")
async def post_publish_member_config(
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    user_id, role, _ = ctx
    member_services.require_admin(role)
    return member_services.publish_config(user_id)


@router.get("/admin/members/{user_id}")
async def get_admin_member_detail(
    user_id: str,
    ctx: Annotated[tuple[str, str, str | None], Depends(_request_context)],
) -> dict[str, object]:
    _, role, _ = ctx
    member_services.require_admin(role)
    return member_services.get_member_detail(user_id)
