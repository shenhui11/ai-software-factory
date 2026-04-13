from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

from apps.backend.domain.models import (
    AuditEvent,
    BenefitDefinition,
    BenefitMapping,
    DraftConfig,
    LedgerEntry,
    LevelRule,
    MemberProfile,
    PointsAccount,
    PublishedConfig,
    RewardRecord,
    TaskDefinition,
    TaskRecord,
    utc_now,
)
from apps.backend.infrastructure.store import store

logger = logging.getLogger(__name__)

KNOWN_BENEFIT_CODES = {"member_badge"}
MAX_LEDGER_LIMIT = 50
RISK_WINDOW_SECONDS = 10
RISK_MAX_EVENTS = 3


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code


def new_request_id() -> str:
    return str(uuid4())


def ensure_member(user_id: str) -> tuple[MemberProfile, PointsAccount]:
    profile = store.member_profiles.get(user_id)
    account = store.points_accounts.get(user_id)
    if profile is None:
        profile = MemberProfile(user_id=user_id)
        store.member_profiles[user_id] = profile
    if account is None:
        account = PointsAccount(user_id=user_id)
        store.points_accounts[user_id] = account
    return profile, account


def get_published_config() -> PublishedConfig:
    return store.published_config


def get_active_level(level_code: str) -> LevelRule:
    for level in get_published_config().levels:
        if level.level_code == level_code:
            return level
    raise DomainError("level_not_found", "Level not found.", {"level_code": level_code}, 404)


def list_unlocked_benefits(level_code: str) -> list[BenefitDefinition]:
    config = get_published_config()
    mapping = config.benefit_mappings.get(level_code)
    if mapping is None:
        return []
    unlocked: list[BenefitDefinition] = []
    for benefit_code in mapping.benefit_codes:
        benefit = config.benefits.get(benefit_code)
        if benefit and benefit.is_enabled:
            unlocked.append(benefit)
    return unlocked


def get_member_summary(user_id: str) -> dict[str, object]:
    profile, account = ensure_member(user_id)
    current_level = get_active_level(profile.current_level)
    next_level = _get_next_level(profile.growth_value)
    growth_to_next = 0 if next_level is None else next_level.growth_threshold - profile.growth_value
    return {
        "membership_status": profile.membership_status,
        "current_level": profile.current_level,
        "current_level_name": current_level.level_name,
        "growth_value": profile.growth_value,
        "next_level": None if next_level is None else next_level.level_code,
        "growth_to_next_level": growth_to_next,
        "points_balance": account.points_balance,
        "unlocked_benefits": [asdict(item) for item in list_unlocked_benefits(profile.current_level)],
    }


def get_dashboard(user_id: str) -> dict[str, object]:
    profile, account = ensure_member(user_id)
    tasks = list_tasks(user_id)
    rewards = [
        asdict(record)
        for record in sorted(
            [reward for reward in store.reward_records if reward.user_id == user_id],
            key=lambda item: item.created_at,
            reverse=True,
        )[:5]
    ]
    summary = get_member_summary(user_id)
    return {
        "membership_status": summary["membership_status"],
        "current_level": summary["current_level"],
        "growth_value": summary["growth_value"],
        "next_level": summary["next_level"],
        "growth_to_next_level": summary["growth_to_next_level"],
        "points_balance": account.points_balance,
        "points_earned_total": account.points_earned_total,
        "unlocked_benefits": summary["unlocked_benefits"],
        "pending_tasks": [task for task in tasks if task["status"] != "completed"],
        "recent_rewards": rewards,
    }


def list_tasks(user_id: str) -> list[dict[str, object]]:
    ensure_member(user_id)
    config = get_published_config()
    today = utc_now().date().isoformat()
    tasks: list[dict[str, object]] = []
    for task in config.tasks.values():
        if not task.is_enabled:
            continue
        record = store.task_records.get((user_id, task.task_code, today))
        progress = 0 if record is None else record.progress
        status = "pending"
        if progress >= task.daily_limit:
            status = "completed"
        tasks.append(
            {
                "task_code": task.task_code,
                "title": task.title,
                "task_type": task.task_type,
                "reward_points": task.reward_points,
                "status": status,
                "progress": progress,
                "daily_reset_at": today,
            }
        )
    return sorted(tasks, key=lambda item: item["task_code"])


def get_points_ledger(
    user_id: str,
    change_type: str | None,
    limit: int,
    cursor: str | None,
) -> dict[str, object]:
    ensure_member(user_id)
    if limit < 1 or limit > MAX_LEDGER_LIMIT:
        raise DomainError("invalid_limit", "Limit is out of range.", {"limit": limit}, 400)
    if change_type not in {None, "earn", "spend"}:
        raise DomainError(
            "invalid_change_type",
            "change_type is invalid.",
            {"change_type": change_type},
            400,
        )
    if cursor not in {None, ""}:
        raise DomainError("invalid_cursor", "Cursor is invalid.", {"cursor": cursor}, 400)
    entries = [item for item in store.ledger_entries if item.user_id == user_id]
    if change_type:
        entries = [item for item in entries if item.change_type == change_type]
    items = [asdict(item) for item in sorted(entries, key=lambda item: item.created_at, reverse=True)[:limit]]
    return {"items": items, "next_cursor": None}


def get_rewards(user_id: str) -> dict[str, object]:
    ensure_member(user_id)
    rewards = [asdict(item) for item in store.reward_records if item.user_id == user_id]
    rewards.sort(key=lambda item: item["created_at"], reverse=True)
    return {"items": rewards}


def perform_check_in(user_id: str, actor_role: str, request_id: str) -> dict[str, object]:
    return _complete_task(
        user_id=user_id,
        actor_role=actor_role,
        task_code="daily_check_in",
        source_type="check_in",
        request_id=request_id,
    )


def perform_task_completion(
    user_id: str,
    actor_role: str,
    task_code: str,
    request_id: str,
) -> dict[str, object]:
    return _complete_task(
        user_id=user_id,
        actor_role=actor_role,
        task_code=task_code,
        source_type="task_completion",
        request_id=request_id,
    )


def get_admin_member_details(target_user_id: str) -> dict[str, object]:
    if target_user_id not in store.member_profiles and target_user_id not in store.points_accounts:
        raise DomainError("member_not_found", "Member not found.", {"user_id": target_user_id}, 404)
    summary = get_member_summary(target_user_id)
    return {
        "member": summary,
        "tasks": list_tasks(target_user_id),
        "ledger": get_points_ledger(target_user_id, None, 20, None)["items"],
    }


def get_config_snapshot() -> dict[str, object]:
    config = get_published_config()
    return {
        "published_version": config.version,
        "published_at": config.published_at,
        "tasks": [asdict(item) for item in config.tasks.values()],
        "levels": [asdict(item) for item in config.levels],
        "benefits": [asdict(item) for item in config.benefits.values()],
        "benefit_mappings": [asdict(item) for item in config.benefit_mappings.values()],
    }


def update_task_config(tasks_payload: list[dict[str, object]], actor_user_id: str, actor_role: str, request_id: str) -> dict[str, object]:
    draft = _get_draft_copy()
    new_tasks: dict[str, TaskDefinition] = {}
    for item in tasks_payload:
        payload = _coerce_payload(item)
        task = TaskDefinition(
            task_code=str(payload["task_code"]),
            title=str(payload["title"]),
            task_type=str(payload["task_type"]),
            reward_points=int(payload["reward_points"]),
            daily_limit=int(payload["daily_limit"]),
            is_enabled=bool(payload["is_enabled"]),
        )
        new_tasks[task.task_code] = task
    draft.tasks = new_tasks
    store.draft_config = draft
    _add_audit(actor_user_id, actor_role, "member_config_tasks_updated", request_id, {"tasks": str(len(new_tasks))})
    return {"draft_tasks": [asdict(item) for item in new_tasks.values()]}


def update_level_config(levels_payload: list[dict[str, object]], actor_user_id: str, actor_role: str, request_id: str) -> dict[str, object]:
    draft = _get_draft_copy()
    draft.levels = [
        LevelRule(
            level_code=str(_coerce_payload(item)["level_code"]),
            level_name=str(_coerce_payload(item)["level_name"]),
            growth_threshold=int(_coerce_payload(item)["growth_threshold"]),
            description=str(_coerce_payload(item)["description"]),
        )
        for item in levels_payload
    ]
    store.draft_config = draft
    _add_audit(actor_user_id, actor_role, "member_config_levels_updated", request_id, {"levels": str(len(draft.levels))})
    return {"draft_levels": [asdict(item) for item in draft.levels]}


def update_benefit_config(
    benefits_payload: list[dict[str, object]],
    mappings_payload: list[dict[str, object]],
    actor_user_id: str,
    actor_role: str,
    request_id: str,
) -> dict[str, object]:
    draft = _get_draft_copy()
    draft.benefits = {
        str(_coerce_payload(item)["benefit_code"]): BenefitDefinition(
            benefit_code=str(_coerce_payload(item)["benefit_code"]),
            title=str(_coerce_payload(item)["title"]),
            description=str(_coerce_payload(item)["description"]),
            is_enabled=bool(_coerce_payload(item)["is_enabled"]),
        )
        for item in benefits_payload
    }
    draft.benefit_mappings = {
        str(_coerce_payload(item)["level_code"]): BenefitMapping(
            level_code=str(_coerce_payload(item)["level_code"]),
            benefit_codes=[str(code) for code in _coerce_payload(item)["benefit_codes"]],
        )
        for item in mappings_payload
    }
    store.draft_config = draft
    _add_audit(actor_user_id, actor_role, "member_config_benefits_updated", request_id, {"benefits": str(len(draft.benefits))})
    return {
        "draft_benefits": [asdict(item) for item in draft.benefits.values()],
        "draft_mappings": [asdict(item) for item in draft.benefit_mappings.values()],
    }


def publish_config(actor_user_id: str, actor_role: str, request_id: str) -> dict[str, object]:
    draft = _get_draft_copy()
    _validate_draft_config(draft)
    version = store.published_config.version + 1
    published = PublishedConfig(
        version=version,
        published_at=utc_now(),
        tasks=deepcopy(draft.tasks),
        levels=deepcopy(draft.levels),
        benefits=deepcopy(draft.benefits),
        benefit_mappings=deepcopy(draft.benefit_mappings),
    )
    store.published_config = published
    for profile in store.member_profiles.values():
        profile.current_config_version = version
    _add_audit(actor_user_id, actor_role, "member_config_published", request_id, {"version": str(version)})
    return {"version": version, "published_at": published.published_at}


def get_audit_events() -> list[dict[str, object]]:
    return [asdict(item) for item in store.audit_events]


def _complete_task(user_id: str, actor_role: str, task_code: str, source_type: str, request_id: str) -> dict[str, object]:
    profile, account = ensure_member(user_id)
    task = get_published_config().tasks.get(task_code)
    if task is None:
        raise DomainError("task_not_found", "Task not found.", {"task_code": task_code}, 404)
    if not task.is_enabled:
        raise DomainError("task_disabled", "Task is disabled.", {"task_code": task_code}, 400)
    action_key = (user_id, source_type, request_id)
    if action_key in store.request_action_index:
        return _build_idempotent_response(profile, account, task_code)
    _enforce_risk_control(user_id, source_type, request_id)
    today = utc_now().date().isoformat()
    record_key = (user_id, task.task_code, today)
    record = store.task_records.get(record_key)
    if record is None:
        record = TaskRecord(user_id=user_id, task_code=task.task_code, task_date=today)
        store.task_records[record_key] = record
    if record.progress >= task.daily_limit:
        raise DomainError("daily_limit_reached", "Daily limit reached.", {"task_code": task.task_code}, 409)
    record.progress += 1
    record.status = "completed" if record.progress >= task.daily_limit else "pending"
    record.completed_at = utc_now()
    record.request_ids.add(request_id)
    store.request_action_index[action_key] = task.task_code
    granted_points = task.reward_points
    account.points_balance += granted_points
    account.points_earned_total += granted_points
    account.last_earned_at = utc_now()
    account.updated_at = utc_now()
    profile.growth_value += granted_points
    previous_level = profile.current_level
    level_up, unlocked = _evaluate_level(profile, request_id)
    profile.updated_at = utc_now()
    ledger = LedgerEntry(
        user_id=user_id,
        request_id=request_id,
        source_type=source_type,
        source_ref_id=task.task_code,
        change_type="earn",
        points_delta=granted_points,
        balance_after=account.points_balance,
    )
    store.ledger_entries.append(ledger)
    _add_audit(user_id, actor_role, f"{source_type}_completed", request_id, {"task_code": task.task_code})
    logger.info("points_granted", extra={"user_id": user_id, "task_code": task.task_code, "request_id": request_id})
    return {
        "success": True,
        "task_code": task.task_code,
        "completion_status": record.status,
        "granted_points": granted_points,
        "points_balance": account.points_balance,
        "current_level": profile.current_level,
        "previous_level": previous_level,
        "level_up": level_up,
        "unlocked_benefits": unlocked,
        "reward_result": {"granted": True, "reward_count": len(unlocked)},
        "request_id": request_id,
    }


def _build_idempotent_response(profile: MemberProfile, account: PointsAccount, task_code: str) -> dict[str, object]:
    return {
        "success": True,
        "task_code": task_code,
        "completion_status": "completed",
        "granted_points": 0,
        "points_balance": account.points_balance,
        "current_level": profile.current_level,
        "level_up": False,
        "unlocked_benefits": [],
        "reward_result": {"granted": False, "reward_count": 0},
    }


def _evaluate_level(profile: MemberProfile, request_id: str) -> tuple[bool, list[dict[str, object]]]:
    target_level = _resolve_level(profile.growth_value)
    if target_level.level_code == profile.current_level:
        profile.membership_status = "growth_member" if profile.current_level != "L1" else "regular"
        return False, []
    profile.current_level = target_level.level_code
    profile.membership_status = "growth_member"
    profile.last_level_up_at = utc_now()
    unlocked = []
    for benefit in list_unlocked_benefits(target_level.level_code):
        reward = RewardRecord(
            user_id=profile.user_id,
            request_id=request_id,
            reward_type="benefit_unlock",
            reward_code=benefit.benefit_code,
            title=benefit.title,
            context={"level_code": target_level.level_code},
        )
        store.reward_records.append(reward)
        unlocked.append(asdict(benefit))
    _add_audit(profile.user_id, "user", "member_level_up", request_id, {"level_code": target_level.level_code})
    logger.info("member_level_up", extra={"user_id": profile.user_id, "level_code": target_level.level_code})
    return True, unlocked


def _resolve_level(growth_value: int) -> LevelRule:
    levels = sorted(get_published_config().levels, key=lambda item: item.growth_threshold)
    active = levels[0]
    for level in levels:
        if growth_value >= level.growth_threshold:
            active = level
    return active


def _get_next_level(growth_value: int) -> LevelRule | None:
    for level in sorted(get_published_config().levels, key=lambda item: item.growth_threshold):
        if level.growth_threshold > growth_value:
            return level
    return None


def _enforce_risk_control(user_id: str, action: str, request_id: str) -> None:
    key = (user_id, action)
    now = utc_now()
    window = store.risk_windows.setdefault(key, [])
    window[:] = [item for item in window if (now - item).total_seconds() < RISK_WINDOW_SECONDS]
    if len(window) >= RISK_MAX_EVENTS:
        raise DomainError(
            "risk_control_blocked",
            "Request blocked by risk control.",
            {"action": action, "request_id": request_id},
            429,
        )
    window.append(now)


def _get_draft_copy() -> DraftConfig:
    return DraftConfig(
        tasks=deepcopy(store.draft_config.tasks),
        levels=deepcopy(store.draft_config.levels),
        benefits=deepcopy(store.draft_config.benefits),
        benefit_mappings=deepcopy(store.draft_config.benefit_mappings),
    )


def _validate_draft_config(draft: DraftConfig) -> None:
    if not draft.tasks:
        raise DomainError("config_validation_failed", "At least one task is required.", {"field": "tasks"}, 400)
    if not draft.levels:
        raise DomainError("config_validation_failed", "At least one level is required.", {"field": "levels"}, 400)
    sorted_levels = sorted(draft.levels, key=lambda item: item.growth_threshold)
    seen_levels: set[str] = set()
    previous_threshold = -1
    for level in sorted_levels:
        if level.level_code in seen_levels:
            raise DomainError("config_validation_failed", "Duplicate level_code found.", {"level_code": level.level_code}, 400)
        if level.growth_threshold < previous_threshold:
            raise DomainError("config_validation_failed", "Level thresholds must be ascending.", {"level_code": level.level_code}, 400)
        seen_levels.add(level.level_code)
        previous_threshold = level.growth_threshold
    for benefit_code, benefit in draft.benefits.items():
        if benefit_code not in KNOWN_BENEFIT_CODES:
            raise DomainError("config_validation_failed", "Unknown benefit_code.", {"benefit_code": benefit_code}, 400)
    for level_code, mapping in draft.benefit_mappings.items():
        if level_code not in seen_levels:
            raise DomainError("config_validation_failed", "Benefit mapping references invalid level.", {"level_code": level_code}, 400)
        for benefit_code in mapping.benefit_codes:
            if benefit_code not in draft.benefits:
                raise DomainError("config_validation_failed", "Benefit mapping references invalid benefit.", {"benefit_code": benefit_code}, 400)


def _add_audit(actor_user_id: str, actor_role: str, action: str, request_id: str, details: dict[str, str]) -> None:
    store.audit_events.append(
        AuditEvent(
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=action,
            request_id=request_id,
            details=details,
        )
    )


def _coerce_payload(item: object) -> dict[str, object]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    raise DomainError("invalid_payload", "Unsupported payload type.", {}, 400)
