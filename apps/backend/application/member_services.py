from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from apps.backend.application.services import DomainError
from apps.backend.domain.models import (
    BenefitConfig,
    LevelConfig,
    MemberAuditEvent,
    MemberConfigSnapshot,
    MemberProfile,
    MemberTaskConfig,
    MemberTaskRecord,
    PointsAccount,
    PointsLedgerEntry,
    RewardRecord,
    utc_now,
)
from apps.backend.infrastructure.store import store

logger = logging.getLogger(__name__)
VALID_CHANGE_TYPES = {"earn", "spend"}
MAX_LEDGER_LIMIT = 100


def require_user(user_id: str | None) -> str:
    if not user_id:
        raise DomainError("unauthorized", "Authentication required.", status_code=401)
    return user_id


def require_admin(user_id: str | None, role: str | None) -> str:
    operator_id = require_user(user_id)
    if role != "admin":
        raise DomainError("forbidden", "Admin role required.", status_code=403)
    return operator_id


def _now_day() -> date:
    return utc_now().date()


def _task_key(user_id: str, task_code: str, task_day: date) -> str:
    return f"{user_id}:{task_code}:{task_day.isoformat()}"


def _get_published_config() -> MemberConfigSnapshot:
    return store.member_published_config


def _clone_config(snapshot: MemberConfigSnapshot) -> MemberConfigSnapshot:
    return deepcopy(snapshot)


def _ensure_member_state(user_id: str) -> tuple[MemberProfile, PointsAccount]:
    profile = store.member_profiles.get(user_id)
    account = store.points_accounts.get(user_id)
    if profile is None:
        profile = MemberProfile(
            user_id=user_id,
            current_config_version=_get_published_config().version,
        )
        store.member_profiles[user_id] = profile
    if account is None:
        account = PointsAccount(user_id=user_id)
        store.points_accounts[user_id] = account
    return profile, account


def _get_task_config(task_code: str, published_only: bool = True) -> MemberTaskConfig:
    config = _get_published_config() if published_only else store.member_working_config
    for task in config.tasks:
        if task.task_code == task_code:
            return task
    raise DomainError("task_not_found", "Task not found.", status_code=404)


def _task_record(user_id: str, task_code: str, task_day: date) -> MemberTaskRecord:
    key = _task_key(user_id, task_code, task_day)
    record = store.member_task_records.get(key)
    if record is None:
        record = MemberTaskRecord(user_id=user_id, task_code=task_code, task_date=task_day)
        store.member_task_records[key] = record
    return record


def _ensure_request_id(request_id: str | None) -> str:
    return request_id or str(uuid4())


def _record_event(
    *,
    user_id: str,
    event_type: str,
    request_id: str,
    details: dict[str, object],
    operator_user_id: str | None = None,
    operator_role: str | None = None,
) -> None:
    event = MemberAuditEvent(
        user_id=user_id,
        event_type=event_type,
        request_id=request_id,
        details=details,
        operator_user_id=operator_user_id,
        operator_role=operator_role,
    )
    store.member_audit_events[event.id] = event
    logger.info("member_event", extra={"event_type": event_type, "user_id": user_id})


def _sorted_levels() -> list[LevelConfig]:
    return sorted(_get_published_config().levels, key=lambda item: item.growth_threshold)


def resolve_level(growth_value: int, levels: list[LevelConfig] | None = None) -> LevelConfig:
    ordered = levels or _sorted_levels()
    current = ordered[0]
    for level in ordered:
        if growth_value >= level.growth_threshold:
            current = level
    return current


def growth_to_next_level(growth_value: int, levels: list[LevelConfig] | None = None) -> tuple[str | None, int]:
    ordered = levels or _sorted_levels()
    for level in ordered:
        if growth_value < level.growth_threshold:
            return level.code, level.growth_threshold - growth_value
    return None, 0


def _unlocked_benefits(level_code: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for benefit in _get_published_config().benefits:
        if benefit.level_code == level_code and benefit.is_enabled:
            items.append(asdict(benefit))
    return items


def _pending_tasks(user_id: str) -> list[dict[str, Any]]:
    task_day = _now_day()
    items: list[dict[str, Any]] = []
    for task in _get_published_config().tasks:
        if not task.is_enabled:
            continue
        record = _task_record(user_id, task.task_code, task_day)
        items.append(
            {
                "task_code": task.task_code,
                "title": task.title,
                "task_type": task.task_type,
                "reward_points": task.reward_points,
                "status": record.status,
                "progress": record.progress,
                "daily_reset_at": f"{task_day.isoformat()}T23:59:59+00:00",
            }
        )
    return items


def _recent_rewards(user_id: str) -> list[dict[str, Any]]:
    rewards = [item for item in store.reward_records.values() if item.user_id == user_id]
    rewards.sort(key=lambda item: item.created_at, reverse=True)
    return [asdict(item) for item in rewards[:5]]


def get_member_summary(user_id: str) -> dict[str, Any]:
    profile, account = _ensure_member_state(user_id)
    next_level, remaining = growth_to_next_level(profile.growth_value)
    return {
        "membership_status": profile.membership_status,
        "current_level": profile.current_level,
        "growth_value": profile.growth_value,
        "next_level": next_level,
        "growth_to_next_level": remaining,
        "points_balance": account.points_balance,
        "unlocked_benefits": _unlocked_benefits(profile.current_level),
    }


def get_member_dashboard(user_id: str) -> dict[str, Any]:
    profile, account = _ensure_member_state(user_id)
    next_level, remaining = growth_to_next_level(profile.growth_value)
    return {
        "membership_status": profile.membership_status,
        "current_level": profile.current_level,
        "growth_value": profile.growth_value,
        "next_level": next_level,
        "growth_to_next_level": remaining,
        "points_balance": account.points_balance,
        "points_earned_total": account.points_earned_total,
        "unlocked_benefits": _unlocked_benefits(profile.current_level),
        "pending_tasks": _pending_tasks(user_id),
        "recent_rewards": _recent_rewards(user_id),
    }


def list_member_tasks(user_id: str) -> dict[str, Any]:
    _ensure_member_state(user_id)
    return {"items": _pending_tasks(user_id), "config_version": _get_published_config().version}


def _recent_earn_events(user_id: str) -> int:
    threshold = utc_now() - timedelta(minutes=1)
    return sum(
        1
        for item in store.points_ledger_entries.values()
        if item.user_id == user_id
        and item.change_type == "earn"
        and item.created_at >= threshold
    )


def _risk_check(user_id: str, request_id: str) -> None:
    for entry in store.points_ledger_entries.values():
        if entry.user_id == user_id and entry.request_id == request_id:
            raise DomainError(
                "duplicate_request",
                "Request has already been processed.",
                details={"request_id": request_id},
                status_code=409,
            )
    if _recent_earn_events(user_id) >= 5:
        raise DomainError(
            "risk_control_blocked",
            "Request blocked by risk control.",
            details={"reason": "too_many_point_events"},
            status_code=429,
        )


def _record_points(
    *,
    user_id: str,
    source_type: str,
    source_ref_id: str,
    points_delta: int,
    request_id: str,
    details: dict[str, object],
) -> PointsLedgerEntry:
    profile, account = _ensure_member_state(user_id)
    _risk_check(user_id, request_id)
    account.points_balance += points_delta
    account.points_earned_total += max(points_delta, 0)
    account.last_earned_at = utc_now()
    account.updated_at = utc_now()
    profile.growth_value += max(points_delta, 0)
    profile.updated_at = utc_now()
    entry = PointsLedgerEntry(
        user_id=user_id,
        source_type=source_type,
        source_ref_id=source_ref_id,
        change_type="earn",
        points_delta=points_delta,
        balance_after=account.points_balance,
        request_id=request_id,
        details=details,
    )
    store.points_ledger_entries[entry.id] = entry
    _record_event(
        user_id=user_id,
        event_type="points_granted",
        request_id=request_id,
        details={"source_type": source_type, "points_delta": points_delta},
    )
    return entry


def _dispatch_level_reward(user_id: str, level_code: str, request_id: str) -> RewardRecord:
    reward = RewardRecord(
        user_id=user_id,
        reward_type="level_up",
        reward_code=level_code,
        title=f"{level_code} 权益已解锁",
        details={"benefits": _unlocked_benefits(level_code)},
        request_id=request_id,
    )
    store.reward_records[reward.id] = reward
    _record_event(
        user_id=user_id,
        event_type="reward_dispatched",
        request_id=request_id,
        details={"reward_type": "level_up", "reward_code": level_code},
    )
    return reward


def _evaluate_level_up(user_id: str, request_id: str) -> tuple[bool, list[dict[str, Any]]]:
    profile, _ = _ensure_member_state(user_id)
    new_level = resolve_level(profile.growth_value)
    if new_level.code == profile.current_level:
        profile.membership_status = "growth_member" if profile.current_level != "level_1" else "regular"
        return False, _unlocked_benefits(profile.current_level)
    profile.current_level = new_level.code
    profile.membership_status = "growth_member"
    profile.last_level_up_at = utc_now()
    profile.current_config_version = _get_published_config().version
    _dispatch_level_reward(user_id, new_level.code, request_id)
    _record_event(
        user_id=user_id,
        event_type="level_up",
        request_id=request_id,
        details={"current_level": new_level.code},
    )
    return True, _unlocked_benefits(new_level.code)


def complete_check_in(user_id: str, request_id: str | None) -> dict[str, Any]:
    req_id = _ensure_request_id(request_id)
    task = _get_task_config("daily_check_in")
    if not task.is_enabled:
        raise DomainError("task_disabled", "Task is disabled.", status_code=400)
    record = _task_record(user_id, task.task_code, _now_day())
    if record.status == "completed":
        raise DomainError("duplicate_check_in", "Check-in already completed today.", status_code=409)
    ledger = _record_points(
        user_id=user_id,
        source_type="check_in",
        source_ref_id=task.task_code,
        points_delta=task.reward_points,
        request_id=req_id,
        details={"task_code": task.task_code},
    )
    record.progress = 1
    record.status = "completed"
    record.completed_at = utc_now()
    record.request_ids.append(req_id)
    level_up, benefits = _evaluate_level_up(user_id, req_id)
    return {
        "success": True,
        "granted_points": task.reward_points,
        "points_balance": ledger.balance_after,
        "current_level": store.member_profiles[user_id].current_level,
        "level_up": level_up,
        "unlocked_benefits": benefits,
    }


def complete_task(user_id: str, task_code: str, request_id: str | None) -> dict[str, Any]:
    req_id = _ensure_request_id(request_id)
    task = _get_task_config(task_code)
    if not task.is_enabled:
        raise DomainError("task_disabled", "Task is disabled.", status_code=400)
    task_day = _now_day()
    record = _task_record(user_id, task_code, task_day)
    if req_id in record.request_ids:
        raise DomainError("duplicate_request", "Request has already been processed.", status_code=409)
    if record.progress >= task.daily_limit:
        raise DomainError("daily_limit_reached", "Task daily limit reached.", status_code=409)
    ledger = _record_points(
        user_id=user_id,
        source_type="task_completion",
        source_ref_id=task_code,
        points_delta=task.reward_points,
        request_id=req_id,
        details={"task_code": task_code},
    )
    record.progress += 1
    record.status = "completed" if record.progress >= task.daily_limit else "pending"
    record.completed_at = utc_now()
    record.request_ids.append(req_id)
    level_up, benefits = _evaluate_level_up(user_id, req_id)
    reward = RewardRecord(
        user_id=user_id,
        reward_type="task_completion",
        reward_code=task_code,
        title=f"{task.title} 奖励已发放",
        details={"points": task.reward_points, "benefits": benefits},
        request_id=req_id,
    )
    store.reward_records[reward.id] = reward
    _record_event(
        user_id=user_id,
        event_type="task_completed",
        request_id=req_id,
        details={"task_code": task_code, "points": task.reward_points},
    )
    return {
        "task_code": task_code,
        "completion_status": record.status,
        "granted_points": task.reward_points,
        "points_balance": ledger.balance_after,
        "level_up": level_up,
        "reward_result": asdict(reward),
    }


def list_points_ledger(user_id: str, change_type: str | None, limit: int, cursor: str | None) -> dict[str, Any]:
    if change_type is not None and change_type not in VALID_CHANGE_TYPES:
        raise DomainError("invalid_change_type", "Invalid change_type.", status_code=400)
    if limit < 1 or limit > MAX_LEDGER_LIMIT:
        raise DomainError("invalid_limit", "Limit is out of range.", status_code=400)
    if cursor is not None and not cursor.isdigit():
        raise DomainError("invalid_cursor", "Cursor must be numeric.", status_code=400)
    offset = int(cursor or 0)
    entries = [item for item in store.points_ledger_entries.values() if item.user_id == user_id]
    if change_type:
        entries = [item for item in entries if item.change_type == change_type]
    entries.sort(key=lambda item: item.created_at, reverse=True)
    sliced = entries[offset: offset + limit]
    next_cursor = offset + limit if offset + limit < len(entries) else None
    return {"items": [asdict(item) for item in sliced], "next_cursor": next_cursor}


def list_rewards(user_id: str) -> dict[str, Any]:
    rewards = [item for item in store.reward_records.values() if item.user_id == user_id]
    rewards.sort(key=lambda item: item.created_at, reverse=True)
    return {"items": [asdict(item) for item in rewards]}


def get_member_config(user_id: str, role: str | None) -> dict[str, Any]:
    require_admin(user_id, role)
    return {
        "working": asdict(store.member_working_config),
        "published": asdict(store.member_published_config),
    }


def _validate_levels(levels: list[dict[str, Any]]) -> list[LevelConfig]:
    seen: set[str] = set()
    parsed: list[LevelConfig] = []
    for item in levels:
        code = str(item["code"])
        if code in seen:
            raise DomainError("duplicate_level_code", "Duplicate level code.", status_code=400)
        seen.add(code)
        parsed.append(
            LevelConfig(
                code=code,
                name=str(item["name"]),
                growth_threshold=int(item["growth_threshold"]),
                description=str(item.get("description", "")),
            )
        )
    ordered = sorted(parsed, key=lambda level: level.growth_threshold)
    if [level.code for level in ordered] != [level.code for level in parsed]:
        raise DomainError("invalid_level_order", "Levels must be sorted by threshold.", status_code=400)
    return parsed


def update_task_config(user_id: str, role: str | None, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    operator_id = require_admin(user_id, role)
    current = _clone_config(store.member_working_config)
    current.tasks = [
        MemberTaskConfig(
            task_code=str(item["task_code"]),
            task_type=str(item["task_type"]),
            title=str(item["title"]),
            description=str(item.get("description", "")),
            is_enabled=bool(item["is_enabled"]),
            reward_points=int(item["reward_points"]),
            daily_limit=int(item["daily_limit"]),
            window_rule=str(item.get("window_rule", "daily")),
            trigger_source=str(item.get("trigger_source", "manual")),
            config_version=current.version,
        )
        for item in tasks
    ]
    current.updated_at = utc_now()
    store.member_working_config = current
    _record_event(user_id=operator_id, event_type="config_tasks_updated", request_id=str(uuid4()), details={}, operator_user_id=operator_id, operator_role=role)
    return asdict(current)


def update_level_config(user_id: str, role: str | None, levels: list[dict[str, Any]]) -> dict[str, Any]:
    operator_id = require_admin(user_id, role)
    current = _clone_config(store.member_working_config)
    current.levels = _validate_levels(levels)
    current.updated_at = utc_now()
    store.member_working_config = current
    _record_event(user_id=operator_id, event_type="config_levels_updated", request_id=str(uuid4()), details={}, operator_user_id=operator_id, operator_role=role)
    return asdict(current)


def update_benefit_config(user_id: str, role: str | None, benefits: list[dict[str, Any]]) -> dict[str, Any]:
    operator_id = require_admin(user_id, role)
    current = _clone_config(store.member_working_config)
    valid_levels = {level.code for level in current.levels}
    parsed: list[BenefitConfig] = []
    for item in benefits:
        level_code = str(item["level_code"])
        if level_code not in valid_levels:
            raise DomainError("invalid_benefit_level", "Benefit references unknown level.", status_code=400)
        parsed.append(
            BenefitConfig(
                benefit_code=str(item["benefit_code"]),
                level_code=level_code,
                name=str(item["name"]),
                description=str(item.get("description", "")),
                is_enabled=bool(item["is_enabled"]),
                metadata=dict(item.get("metadata", {})),
            )
        )
    current.benefits = parsed
    current.updated_at = utc_now()
    store.member_working_config = current
    _record_event(user_id=operator_id, event_type="config_benefits_updated", request_id=str(uuid4()), details={}, operator_user_id=operator_id, operator_role=role)
    return asdict(current)


def publish_member_config(user_id: str, role: str | None) -> dict[str, Any]:
    operator_id = require_admin(user_id, role)
    current = _clone_config(store.member_working_config)
    current.version = store.member_published_config.version + 1
    current.published_at = utc_now()
    current.updated_at = utc_now()
    for task in current.tasks:
        task.config_version = current.version
        task.updated_at = utc_now()
    store.member_published_config = current
    store.member_working_config = _clone_config(current)
    request_id = str(uuid4())
    _record_event(
        user_id=operator_id,
        event_type="config_published",
        request_id=request_id,
        details={"version": current.version},
        operator_user_id=operator_id,
        operator_role=role,
    )
    return {
        "version": current.version,
        "published_at": current.published_at,
        "request_id": request_id,
    }


def get_member_admin_detail(operator_id: str | None, role: str | None, user_id: str) -> dict[str, Any]:
    require_admin(operator_id, role)
    profile, account = _ensure_member_state(user_id)
    ledger = list_points_ledger(user_id=user_id, change_type=None, limit=20, cursor=None)
    rewards = list_rewards(user_id)
    return {
        "profile": asdict(profile),
        "points_account": asdict(account),
        "tasks": _pending_tasks(user_id),
        "ledger": ledger["items"],
        "rewards": rewards["items"][:10],
    }
