from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from uuid import uuid4

from apps.backend.application.services import DomainError
from apps.backend.domain.member_models import (
    BenefitMapping,
    LevelConfig,
    MemberConfigSnapshot,
    MemberEvent,
    MemberProfile,
    MemberTaskConfig,
    PointsAccount,
    PointsLedgerEntry,
    RewardRecord,
    UserTaskState,
)
from apps.backend.domain.models import utc_now
from apps.backend.infrastructure.member_store import member_store

logger = logging.getLogger(__name__)
MAX_REQUESTS_PER_DAY = 5


def get_actor_context(user_id: str | None, role: str | None) -> tuple[str, str]:
    if not user_id:
        raise DomainError("auth_required", "Authentication required.", status_code=401)
    return user_id, role or "user"


def require_admin(role: str) -> None:
    if role != "admin":
        raise DomainError("forbidden", "Admin role required.", status_code=403)


def ensure_member(user_id: str) -> tuple[MemberProfile, PointsAccount]:
    profile = member_store.member_profiles.get(user_id)
    account = member_store.points_accounts.get(user_id)
    if profile is None:
        profile = MemberProfile(user_id=user_id)
        member_store.member_profiles[user_id] = profile
    if account is None:
        account = PointsAccount(user_id=user_id)
        member_store.points_accounts[user_id] = account
    return profile, account


def get_published_config() -> MemberConfigSnapshot:
    return deepcopy(member_store.published_config)


def list_visible_tasks(user_id: str) -> list[dict[str, object]]:
    ensure_member(user_id)
    today = utc_now().date()
    tasks: list[dict[str, object]] = []
    for task in get_published_config().tasks:
        if not task.enabled:
            continue
        state = _get_task_state(user_id, task.task_code)
        progress = state.completed_today if state.last_completed_on == today else 0
        status = "completed" if progress >= task.daily_limit else "available"
        tasks.append(
            {
                "task_code": task.task_code,
                "title": task.title,
                "task_type": task.task_type,
                "reward_points": task.reward_points,
                "status": status,
                "progress": progress,
                "daily_reset_at": today.isoformat(),
            }
        )
    return tasks


def get_member_summary(user_id: str) -> dict[str, object]:
    profile, account = ensure_member(user_id)
    config = get_published_config()
    current_level = _resolve_level(config.levels, profile.growth_value)
    unlocked = _resolve_unlocked_benefits(config, current_level.level)
    next_level = _next_level(config.levels, current_level.level)
    return {
        "membership_status": _membership_status_for_level(current_level.level),
        "current_level": current_level.level,
        "growth_value": profile.growth_value,
        "next_level": next_level.level if next_level else None,
        "growth_to_next_level": _growth_to_next_level(profile.growth_value, next_level),
        "points_balance": account.points_balance,
        "unlocked_benefits": unlocked,
    }


def get_dashboard(user_id: str) -> dict[str, object]:
    summary = get_member_summary(user_id)
    _, account = ensure_member(user_id)
    rewards = [
        asdict(reward)
        for reward in member_store.reward_records
        if reward.user_id == user_id
    ][-5:]
    return {
        **summary,
        "points_earned_total": account.points_earned_total,
        "tasks": list_visible_tasks(user_id),
        "recent_rewards": rewards,
    }


def perform_check_in(user_id: str, actor_id: str, request_id: str | None) -> dict[str, object]:
    return _apply_task(user_id, "daily_check_in", actor_id, request_id)


def complete_task(
    user_id: str,
    task_code: str,
    actor_id: str,
    request_id: str | None,
) -> dict[str, object]:
    return _apply_task(user_id, task_code, actor_id, request_id)


def get_ledger(
    user_id: str,
    change_type: str | None,
    limit: int,
    cursor: str | None,
) -> dict[str, object]:
    if limit < 1 or limit > 100:
        raise DomainError("invalid_limit", "Limit must be between 1 and 100.", status_code=400)
    if change_type is not None and change_type not in {"earn", "spend"}:
        raise DomainError("invalid_change_type", "Unsupported change_type.", status_code=400)
    if cursor is not None and not cursor.isdigit():
        raise DomainError("invalid_cursor", "Cursor must be numeric.", status_code=400)
    offset = int(cursor) if cursor else 0
    entries = [entry for entry in member_store.ledger_entries if entry.user_id == user_id]
    if change_type is not None:
        entries = [entry for entry in entries if entry.change_type == change_type]
    items = [asdict(entry) for entry in entries[offset : offset + limit]]
    next_cursor = offset + limit if offset + limit < len(entries) else None
    return {"items": items, "next_cursor": next_cursor}


def get_rewards(user_id: str) -> dict[str, object]:
    items = [
        asdict(record) for record in member_store.reward_records if record.user_id == user_id
    ]
    return {"items": items}


def get_admin_config() -> dict[str, object]:
    published = get_published_config()
    staged = deepcopy(member_store.staged_config)
    return {"published": _config_to_dict(published), "staged": _config_to_dict(staged)}


def update_task_config(tasks: list[dict[str, object]], actor_id: str) -> dict[str, object]:
    staged = deepcopy(member_store.staged_config)
    staged.tasks = [_task_from_payload(task) for task in tasks]
    member_store.staged_config = staged
    _record_event("config_tasks_updated", actor_id, actor_id, "config_update", {"count": len(tasks)})
    return _config_to_dict(staged)


def update_level_config(levels: list[dict[str, object]], actor_id: str) -> dict[str, object]:
    staged = deepcopy(member_store.staged_config)
    parsed = [_level_from_payload(level) for level in levels]
    _validate_levels(parsed)
    staged.levels = parsed
    member_store.staged_config = staged
    _record_event("config_levels_updated", actor_id, actor_id, "config_update", {"count": len(levels)})
    return _config_to_dict(staged)


def update_benefit_config(payload: dict[str, list[dict[str, object]]], actor_id: str) -> dict[str, object]:
    staged = deepcopy(member_store.staged_config)
    staged.benefits = [
        _benefit_from_payload(item) for item in payload["benefits"]
    ]
    staged.mappings = [
        BenefitMapping(level=int(item["level"]), benefit_code=str(item["benefit_code"]))
        for item in payload["mappings"]
    ]
    _validate_benefits(staged)
    member_store.staged_config = staged
    _record_event("config_benefits_updated", actor_id, actor_id, "config_update", {"count": len(staged.benefits)})
    return _config_to_dict(staged)


def publish_config(actor_id: str) -> dict[str, object]:
    staged = deepcopy(member_store.staged_config)
    _validate_levels(staged.levels)
    _validate_benefits(staged)
    staged.version = member_store.next_config_version
    staged.published_at = utc_now()
    member_store.next_config_version += 1
    member_store.staged_config = deepcopy(staged)
    member_store.published_config = staged
    _record_event("config_published", actor_id, actor_id, "config_publish", {"version": staged.version})
    return {"version": staged.version, "published_at": staged.published_at}


def get_member_detail(user_id: str) -> dict[str, object]:
    summary = get_dashboard(user_id)
    ledger = get_ledger(user_id, None, 20, None)
    return {"member": summary, "ledger": ledger["items"]}


def _apply_task(
    user_id: str,
    task_code: str,
    actor_id: str,
    request_id: str | None,
) -> dict[str, object]:
    profile, account = ensure_member(user_id)
    task = _get_enabled_task(task_code)
    current_request_id = request_id or str(uuid4())
    state = _get_task_state(user_id, task_code)
    _enforce_risk_control(task, state, current_request_id)
    granted_points = task.reward_points
    _credit_points(account, granted_points)
    _write_ledger(user_id, task_code, granted_points, account.points_balance, current_request_id)
    _mark_task_completed(state, current_request_id)
    level_result = _evaluate_level(profile, actor_id, current_request_id)
    reward_result = _create_reward(user_id, task_code, actor_id, current_request_id)
    _record_event(
        "points_granted",
        user_id,
        actor_id,
        current_request_id,
        {"task_code": task_code, "points": granted_points},
    )
    return {
        "success": True,
        "task_code": task_code,
        "completion_status": "completed",
        "granted_points": granted_points,
        "points_balance": account.points_balance,
        "current_level": profile.current_level,
        "level_up": level_result["level_up"],
        "unlocked_benefits": level_result["unlocked_benefits"],
        "reward_result": reward_result,
    }


def _get_enabled_task(task_code: str) -> MemberTaskConfig:
    for task in get_published_config().tasks:
        if task.task_code == task_code and task.enabled:
            return task
    raise DomainError("task_not_available", "Task is not available.", status_code=404)


def _enforce_risk_control(
    task: MemberTaskConfig,
    state: UserTaskState,
    request_id: str,
) -> None:
    today = utc_now().date()
    if state.last_request_id == request_id:
        raise DomainError("duplicate_request", "Duplicate request detected.", status_code=409)
    if state.last_completed_on != today:
        state.completed_today = 0
    if state.completed_today >= task.daily_limit:
        raise DomainError("daily_limit_reached", "Task daily limit reached.", status_code=409)
    if state.completed_today >= MAX_REQUESTS_PER_DAY:
        raise DomainError("risk_control_blocked", "Request blocked by risk control.", status_code=429)


def _credit_points(account: PointsAccount, amount: int) -> None:
    account.points_balance += amount
    account.points_earned_total += amount
    account.last_earned_at = utc_now()
    account.updated_at = utc_now()


def _write_ledger(
    user_id: str,
    task_code: str,
    amount: int,
    balance_after: int,
    request_id: str,
) -> None:
    source_type = "check_in" if task_code == "daily_check_in" else "task_completion"
    member_store.ledger_entries.append(
        PointsLedgerEntry(
            user_id=user_id,
            source_type=source_type,
            source_ref_id=task_code,
            change_type="earn",
            points_delta=amount,
            balance_after=balance_after,
            request_id=request_id,
        )
    )


def _mark_task_completed(state: UserTaskState, request_id: str) -> None:
    today = utc_now().date()
    if state.last_completed_on != today:
        state.completed_today = 0
    state.completed_today += 1
    state.total_completed += 1
    state.last_completed_on = today
    state.last_request_id = request_id
    state.updated_at = utc_now()


def _evaluate_level(
    profile: MemberProfile,
    actor_id: str,
    request_id: str,
) -> dict[str, object]:
    profile.growth_value += member_store.ledger_entries[-1].points_delta
    config = get_published_config()
    new_level = _resolve_level(config.levels, profile.growth_value)
    level_up = new_level.level > profile.current_level
    if level_up:
        profile.current_level = new_level.level
        profile.membership_status = _membership_status_for_level(new_level.level)
        profile.last_level_up_at = utc_now()
        reward = RewardRecord(
            user_id=profile.user_id,
            reward_type="level_up",
            reward_code=f"level_{new_level.level}",
            message=f"Unlocked level {new_level.name}",
            request_id=request_id,
        )
        member_store.reward_records.append(reward)
        _record_event(
            "member_level_up",
            profile.user_id,
            actor_id,
            request_id,
            {"level": new_level.level},
        )
    profile.current_config_version = config.version
    profile.updated_at = utc_now()
    return {
        "level_up": level_up,
        "unlocked_benefits": _resolve_unlocked_benefits(config, profile.current_level),
    }


def _create_reward(
    user_id: str,
    task_code: str,
    actor_id: str,
    request_id: str,
) -> dict[str, object]:
    reward = RewardRecord(
        user_id=user_id,
        reward_type="check_in" if task_code == "daily_check_in" else "task_completion",
        reward_code=task_code,
        message=f"Reward granted for {task_code}",
        request_id=request_id,
    )
    member_store.reward_records.append(reward)
    _record_event(
        "reward_dispatched",
        user_id,
        actor_id,
        request_id,
        {"reward_code": task_code},
    )
    return asdict(reward)


def _record_event(
    event_type: str,
    user_id: str,
    actor_id: str,
    request_id: str,
    details: dict[str, object],
) -> None:
    event = MemberEvent(
        user_id=user_id,
        event_type=event_type,
        request_id=request_id,
        details=details,
        actor_id=actor_id,
    )
    member_store.member_events.append(event)
    logger.info("member_event", extra={"event": asdict(event)})


def _resolve_level(levels: list[LevelConfig], growth_value: int) -> LevelConfig:
    ordered = sorted(levels, key=lambda item: item.growth_threshold)
    resolved = ordered[0]
    for level in ordered:
        if growth_value >= level.growth_threshold:
            resolved = level
    return resolved


def _next_level(levels: list[LevelConfig], current_level: int) -> LevelConfig | None:
    ordered = sorted(levels, key=lambda item: item.level)
    for level in ordered:
        if level.level > current_level:
            return level
    return None


def _growth_to_next_level(growth_value: int, next_level: LevelConfig | None) -> int:
    if next_level is None:
        return 0
    return max(next_level.growth_threshold - growth_value, 0)


def _resolve_unlocked_benefits(config: MemberConfigSnapshot, level: int) -> list[dict[str, object]]:
    benefit_map = {benefit.benefit_code: benefit for benefit in config.benefits if benefit.enabled}
    unlocked: list[dict[str, object]] = []
    for mapping in config.mappings:
        if mapping.level > level or mapping.benefit_code not in benefit_map:
            continue
        benefit = benefit_map[mapping.benefit_code]
        unlocked.append({"benefit_code": benefit.benefit_code, "name": benefit.name})
    return unlocked


def _membership_status_for_level(level: int) -> str:
    return "growth_member" if level > 1 else "regular"


def _get_task_state(user_id: str, task_code: str) -> UserTaskState:
    key = (user_id, task_code)
    state = member_store.user_tasks.get(key)
    if state is None:
        state = UserTaskState(user_id=user_id, task_code=task_code)
        member_store.user_tasks[key] = state
    return state


def _validate_levels(levels: list[LevelConfig]) -> None:
    if not levels:
        raise DomainError("invalid_levels", "At least one level is required.", status_code=400)
    ordered = sorted(levels, key=lambda item: item.growth_threshold)
    seen_levels: set[int] = set()
    last_threshold = -1
    for level in ordered:
        if level.level in seen_levels:
            raise DomainError("duplicate_level_code", "Duplicate level code.", status_code=400)
        if level.growth_threshold < last_threshold:
            raise DomainError("invalid_level_threshold", "Level thresholds must be ordered.", status_code=400)
        seen_levels.add(level.level)
        last_threshold = level.growth_threshold


def _validate_benefits(config: MemberConfigSnapshot) -> None:
    valid_levels = {level.level for level in config.levels}
    valid_benefits = {benefit.benefit_code for benefit in config.benefits}
    for mapping in config.mappings:
        if mapping.level not in valid_levels:
            raise DomainError("invalid_benefit_level", "Benefit mapping references unknown level.", status_code=400)
        if mapping.benefit_code not in valid_benefits:
            raise DomainError("invalid_benefit_code", "Benefit mapping references unknown benefit.", status_code=400)


def _config_to_dict(config: MemberConfigSnapshot) -> dict[str, object]:
    return {
        "version": config.version,
        "published_at": config.published_at,
        "tasks": [asdict(task) for task in config.tasks],
        "levels": [asdict(level) for level in config.levels],
        "benefits": [asdict(item) for item in config.benefits],
        "mappings": [asdict(item) for item in config.mappings],
    }


def _task_from_payload(payload: dict[str, object]) -> MemberTaskConfig:
    return MemberTaskConfig(
        task_code=str(payload["task_code"]),
        title=str(payload["title"]),
        task_type=str(payload["task_type"]),
        reward_points=int(payload["reward_points"]),
        enabled=bool(payload.get("enabled", True)),
        daily_limit=int(payload.get("daily_limit", 1)),
    )


def _level_from_payload(payload: dict[str, object]) -> LevelConfig:
    return LevelConfig(
        level=int(payload["level"]),
        name=str(payload["name"]),
        growth_threshold=int(payload["growth_threshold"]),
        description=str(payload["description"]),
    )


def _benefit_from_payload(payload: dict[str, object]) -> object:
    from apps.backend.domain.member_models import BenefitConfig

    return BenefitConfig(
        benefit_code=str(payload["benefit_code"]),
        name=str(payload["name"]),
        description=str(payload["description"]),
        enabled=bool(payload.get("enabled", True)),
    )
