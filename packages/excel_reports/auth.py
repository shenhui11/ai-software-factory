from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from packages.excel_reports.models import AuditLog, UserContext
from packages.excel_reports.store import get_store


def _record_denied_auth(request: Request, actor_user_id: str, tenant_id: str) -> None:
    get_store().audit_logs.append(
        AuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action=f"{request.method} {request.url.path}",
            target_id=request.path_params.get("upload_id") or request.path_params.get("report_id") or "-",
            result="denied",
        )
    )


def get_current_user(
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
) -> UserContext:
    if not x_user_id or not x_tenant_id or not x_role:
        _record_denied_auth(request, "anonymous", x_tenant_id or "unknown")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthenticated", "message": "Authentication headers are required."},
        )
    if x_role not in {"admin", "analyst", "viewer"}:
        _record_denied_auth(request, x_user_id, x_tenant_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Unsupported role."},
        )
    return UserContext(user_id=x_user_id, tenant_id=x_tenant_id, role=x_role)


def require_role(user: UserContext, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Insufficient permissions."},
        )
