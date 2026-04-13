from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from apps.backend.api.schemas import (
    PublishConfigResponse,
    UpdateBenefitsRequest,
    UpdateLevelsRequest,
    UpdateTasksRequest,
)
from apps.backend.application import services
from apps.backend.application.services import DomainError

router = APIRouter(prefix="/api/v1")


def get_request_context(
    x_user_id: Annotated[str | None, Header()] = None,
    x_role: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if not x_user_id:
        raise DomainError("unauthorized", "Authentication required.", {}, 401)
    return {
        "user_id": x_user_id,
        "role": x_role or "user",
        "request_id": x_request_id or services.new_request_id(),
    }


def require_admin(context: Annotated[dict[str, str], Depends(get_request_context)]) -> dict[str, str]:
    if context["role"] != "admin":
        raise DomainError("forbidden", "Admin role required.", {}, 403)
    return context


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/members/me")
async def get_member_me(context: Annotated[dict[str, str], Depends(get_request_context)]) -> dict[str, object]:
    return services.get_member_summary(context["user_id"])


@router.get("/members/me/dashboard")
async def get_member_dashboard(context: Annotated[dict[str, str], Depends(get_request_context)]) -> dict[str, object]:
    return services.get_dashboard(context["user_id"])


@router.get("/members/me/tasks")
async def get_member_tasks(context: Annotated[dict[str, str], Depends(get_request_context)]) -> dict[str, object]:
    return {"items": services.list_tasks(context["user_id"])}


@router.post("/members/me/check-ins")
async def post_member_check_in(
    response: Response,
    context: Annotated[dict[str, str], Depends(get_request_context)],
) -> dict[str, object]:
    result = services.perform_check_in(context["user_id"], context["role"], context["request_id"])
    response.headers["X-Request-Id"] = context["request_id"]
    return result


@router.post("/members/me/tasks/{task_code}/complete")
async def post_task_completion(
    task_code: str,
    response: Response,
    context: Annotated[dict[str, str], Depends(get_request_context)],
) -> dict[str, object]:
    result = services.perform_task_completion(
        context["user_id"],
        context["role"],
        task_code,
        context["request_id"],
    )
    response.headers["X-Request-Id"] = context["request_id"]
    return result


@router.get("/members/me/points/ledger")
async def get_member_ledger(
    context: Annotated[dict[str, str], Depends(get_request_context)],
    change_type: str | None = Query(default=None),
    limit: int = Query(default=20),
    cursor: str | None = Query(default=None),
) -> dict[str, object]:
    return services.get_points_ledger(context["user_id"], change_type, limit, cursor)


@router.get("/members/me/rewards")
async def get_member_rewards(context: Annotated[dict[str, str], Depends(get_request_context)]) -> dict[str, object]:
    return services.get_rewards(context["user_id"])


@router.get("/admin/member-config")
async def get_admin_member_config(context: Annotated[dict[str, str], Depends(require_admin)]) -> dict[str, object]:
    return services.get_config_snapshot()


@router.put("/admin/member-config/tasks")
async def put_admin_member_tasks(
    payload: UpdateTasksRequest,
    context: Annotated[dict[str, str], Depends(require_admin)],
) -> dict[str, object]:
    return services.update_task_config(payload.tasks, context["user_id"], context["role"], context["request_id"])


@router.put("/admin/member-config/levels")
async def put_admin_member_levels(
    payload: UpdateLevelsRequest,
    context: Annotated[dict[str, str], Depends(require_admin)],
) -> dict[str, object]:
    return services.update_level_config(payload.levels, context["user_id"], context["role"], context["request_id"])


@router.put("/admin/member-config/benefits")
async def put_admin_member_benefits(
    payload: UpdateBenefitsRequest,
    context: Annotated[dict[str, str], Depends(require_admin)],
) -> dict[str, object]:
    return services.update_benefit_config(
        payload.benefits,
        payload.mappings,
        context["user_id"],
        context["role"],
        context["request_id"],
    )


@router.post("/admin/member-config:publish", response_model=PublishConfigResponse)
async def post_admin_member_publish(
    context: Annotated[dict[str, str], Depends(require_admin)],
) -> dict[str, object]:
    return services.publish_config(context["user_id"], context["role"], context["request_id"])


@router.get("/admin/members/{user_id}")
async def get_admin_member_details(
    user_id: str,
    context: Annotated[dict[str, str], Depends(require_admin)],
) -> dict[str, object]:
    return services.get_admin_member_details(user_id)
