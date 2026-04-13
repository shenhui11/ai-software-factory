from __future__ import annotations

from fastapi import APIRouter, Header, Query

from apps.backend.api.member_schemas import (
    BenefitConfigUpdateRequest,
    LevelConfigUpdateRequest,
    TaskConfigUpdateRequest,
)
from apps.backend.application import member_services

router = APIRouter(prefix="/api/v1")


@router.get("/members/me")
async def get_member_summary(
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.get_member_summary(member_services.require_user(x_user_id))


@router.get("/members/me/dashboard")
async def get_member_dashboard(
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.get_member_dashboard(member_services.require_user(x_user_id))


@router.get("/members/me/tasks")
async def get_member_tasks(
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.list_member_tasks(member_services.require_user(x_user_id))


@router.post("/members/me/check-ins")
async def create_check_in(
    x_user_id: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.complete_check_in(
        user_id=member_services.require_user(x_user_id),
        request_id=x_request_id,
    )


@router.post("/members/me/tasks/{task_code}/complete")
async def complete_member_task(
    task_code: str,
    x_user_id: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.complete_task(
        user_id=member_services.require_user(x_user_id),
        task_code=task_code,
        request_id=x_request_id,
    )


@router.get("/members/me/points/ledger")
async def get_points_ledger(
    x_user_id: str | None = Header(default=None),
    cursor: str | None = None,
    limit: int = Query(default=20),
    change_type: str | None = None,
) -> dict[str, object]:
    return member_services.list_points_ledger(
        user_id=member_services.require_user(x_user_id),
        change_type=change_type,
        limit=limit,
        cursor=cursor,
    )


@router.get("/members/me/rewards")
async def get_reward_records(
    x_user_id: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.list_rewards(member_services.require_user(x_user_id))


@router.get("/admin/member-config")
async def get_member_config(
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.get_member_config(x_user_id, x_user_role)


@router.put("/admin/member-config/tasks")
async def put_task_config(
    payload: TaskConfigUpdateRequest,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.update_task_config(x_user_id, x_user_role, payload.model_dump()["tasks"])


@router.put("/admin/member-config/levels")
async def put_level_config(
    payload: LevelConfigUpdateRequest,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.update_level_config(
        x_user_id,
        x_user_role,
        payload.model_dump()["levels"],
    )


@router.put("/admin/member-config/benefits")
async def put_benefit_config(
    payload: BenefitConfigUpdateRequest,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.update_benefit_config(
        x_user_id,
        x_user_role,
        payload.model_dump()["benefits"],
    )


@router.post("/admin/member-config:publish")
async def publish_member_config(
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.publish_member_config(x_user_id, x_user_role)


@router.get("/admin/members/{user_id}")
async def get_member_detail(
    user_id: str,
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> dict[str, object]:
    return member_services.get_member_admin_detail(x_user_id, x_user_role, user_id)
