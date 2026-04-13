from __future__ import annotations

from apps.backend.application import services
from apps.backend.application.services import DomainError
from apps.backend.infrastructure.store import store


def test_member_summary_initializes_profile_and_account() -> None:
    summary = services.get_member_summary("user-1")
    assert summary["membership_status"] == "regular"
    assert summary["current_level"] == "L1"
    assert summary["points_balance"] == 0


def test_invalid_change_type_is_rejected() -> None:
    services.ensure_member("user-1")
    try:
        services.get_points_ledger("user-1", "bad", 20, None)
    except DomainError as exc:
        assert exc.code == "invalid_change_type"
    else:
        raise AssertionError("Expected DomainError")


def test_invalid_config_publish_fails_for_unknown_benefit() -> None:
    services.update_level_config(
        [
            {
                "level_code": "L1",
                "level_name": "Regular",
                "growth_threshold": 0,
                "description": "base",
            }
        ],
        "admin-1",
        "admin",
        "req-levels",
    )
    services.update_task_config(
        [
            {
                "task_code": "daily_check_in",
                "title": "Daily Check-in",
                "task_type": "check_in",
                "reward_points": 10,
                "daily_limit": 1,
                "is_enabled": True,
            }
        ],
        "admin-1",
        "admin",
        "req-tasks",
    )
    services.update_benefit_config(
        [
            {
                "benefit_code": "unknown_badge",
                "title": "Unknown",
                "description": "invalid",
                "is_enabled": True,
            }
        ],
        [{"level_code": "L1", "benefit_codes": ["unknown_badge"]}],
        "admin-1",
        "admin",
        "req-benefits",
    )
    try:
        services.publish_config("admin-1", "admin", "req-publish")
    except DomainError as exc:
        assert exc.code == "config_validation_failed"
    else:
        raise AssertionError("Expected DomainError")


def test_risk_control_blocks_high_frequency_requests() -> None:
    for index in range(3):
        services._enforce_risk_control("user-1", "task_completion", f"req-{index}")
    try:
        services._enforce_risk_control("user-1", "task_completion", "req-4")
    except DomainError as exc:
        assert exc.code == "risk_control_blocked"
        assert exc.status_code == 429
    else:
        raise AssertionError("Expected DomainError")


def test_publish_promotes_draft_without_exposing_unpublished_changes() -> None:
    original_points = store.published_config.tasks["complete_profile"].reward_points
    services.update_task_config(
        [
            {
                "task_code": "daily_check_in",
                "title": "Daily Check-in",
                "task_type": "check_in",
                "reward_points": 10,
                "daily_limit": 1,
                "is_enabled": True,
            },
            {
                "task_code": "complete_profile",
                "title": "Complete Profile",
                "task_type": "manual",
                "reward_points": 99,
                "daily_limit": 1,
                "is_enabled": True,
            },
        ],
        "admin-1",
        "admin",
        "req-update",
    )
    assert store.published_config.tasks["complete_profile"].reward_points == original_points
