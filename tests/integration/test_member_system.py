from __future__ import annotations

from apps.backend.infrastructure.store import store


USER_HEADERS = {"x-user-id": "user-1"}
ADMIN_HEADERS = {"x-user-id": "ops-1", "x-user-role": "admin"}


def test_member_profile_and_dashboard_require_auth_and_return_member_state(client) -> None:
    unauthorized = client.get("/api/v1/members/me")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "unauthorized"

    profile = client.get("/api/v1/members/me", headers=USER_HEADERS)
    dashboard = client.get("/api/v1/members/me/dashboard", headers=USER_HEADERS)

    assert profile.status_code == 200
    assert profile.json()["membership_status"] == "regular"
    assert profile.json()["current_level"] == "level_1"
    assert profile.json()["points_balance"] == 0
    assert dashboard.status_code == 200
    assert dashboard.json()["current_level"] == profile.json()["current_level"]
    assert isinstance(dashboard.json()["pending_tasks"], list)


def test_tasks_check_in_and_ledger_flow(client) -> None:
    tasks_response = client.get("/api/v1/members/me/tasks", headers=USER_HEADERS)
    assert tasks_response.status_code == 200
    assert tasks_response.json()["items"][0]["task_code"] == "daily_check_in"

    check_in = client.post(
        "/api/v1/members/me/check-ins",
        headers={**USER_HEADERS, "x-request-id": "check-1"},
    )
    assert check_in.status_code == 200
    assert check_in.json()["granted_points"] == 10

    ledger = client.get(
        "/api/v1/members/me/points/ledger",
        headers=USER_HEADERS,
        params={"change_type": "earn", "limit": 10},
    )
    assert ledger.status_code == 200
    item = ledger.json()["items"][0]
    assert item["source_type"] == "check_in"
    assert item["source_ref_id"] == "daily_check_in"


def test_task_completion_levels_up_and_creates_rewards(client) -> None:
    response = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers={**USER_HEADERS, "x-request-id": "task-1"},
    )
    assert response.status_code == 200
    assert response.json()["level_up"] is False

    profile = client.get("/api/v1/members/me", headers=USER_HEADERS)
    assert profile.json()["current_level"] == "level_1"

    check_in = client.post(
        "/api/v1/members/me/check-ins",
        headers={**USER_HEADERS, "x-request-id": "check-2"},
    )
    assert check_in.status_code == 200
    assert check_in.json()["level_up"] is True

    profile_after = client.get("/api/v1/members/me", headers=USER_HEADERS)
    dashboard = client.get("/api/v1/members/me/dashboard", headers=USER_HEADERS)
    rewards = client.get("/api/v1/members/me/rewards", headers=USER_HEADERS)

    assert profile_after.json()["membership_status"] == "growth_member"
    assert profile_after.json()["current_level"] == "level_2"
    assert dashboard.json()["unlocked_benefits"][0]["benefit_code"] == "growth_badge"
    reward_codes = {item["reward_code"] for item in rewards.json()["items"]}
    assert "level_2" in reward_codes
    assert "complete_profile" in reward_codes


def test_duplicate_check_in_and_duplicate_request_are_blocked(client) -> None:
    first = client.post(
        "/api/v1/members/me/check-ins",
        headers={**USER_HEADERS, "x-request-id": "same-check"},
    )
    second = client.post(
        "/api/v1/members/me/check-ins",
        headers={**USER_HEADERS, "x-request-id": "same-check"},
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_check_in"

    task_first = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers={**USER_HEADERS, "x-request-id": "same-task"},
    )
    task_second = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers={**USER_HEADERS, "x-request-id": "same-task"},
    )
    assert task_first.status_code == 200
    assert task_second.status_code == 409
    assert task_second.json()["error"]["code"] == "duplicate_request"

    ledger = client.get("/api/v1/members/me/points/ledger", headers=USER_HEADERS)
    matching = [item for item in ledger.json()["items"] if item["request_id"] == "same-task"]
    assert len(matching) == 1


def test_admin_can_update_and_publish_config_then_user_reads_published_version(client) -> None:
    forbidden = client.get("/api/v1/admin/member-config", headers=USER_HEADERS)
    assert forbidden.status_code == 403

    snapshot = client.get("/api/v1/admin/member-config", headers=ADMIN_HEADERS)
    assert snapshot.status_code == 200
    original_version = snapshot.json()["published"]["version"]

    update_tasks = client.put(
        "/api/v1/admin/member-config/tasks",
        headers=ADMIN_HEADERS,
        json={
            "tasks": [
                {
                    "task_code": "daily_check_in",
                    "task_type": "check_in",
                    "title": "每日签到",
                    "description": "每日签到获取成长积分",
                    "is_enabled": True,
                    "reward_points": 12,
                    "daily_limit": 1,
                    "window_rule": "daily",
                    "trigger_source": "member_panel",
                }
            ]
        },
    )
    assert update_tasks.status_code == 200

    update_levels = client.put(
        "/api/v1/admin/member-config/levels",
        headers=ADMIN_HEADERS,
        json={
            "levels": [
                {"code": "level_1", "name": "普通用户", "growth_threshold": 0, "description": "默认"},
                {"code": "level_2", "name": "成长会员", "growth_threshold": 12, "description": "升级"},
            ]
        },
    )
    assert update_levels.status_code == 200

    update_benefits = client.put(
        "/api/v1/admin/member-config/benefits",
        headers=ADMIN_HEADERS,
        json={
            "benefits": [
                {
                    "benefit_code": "growth_badge_v2",
                    "level_code": "level_2",
                    "name": "新成长标识",
                    "description": "升级后显示",
                    "is_enabled": True,
                    "metadata": {"badge": "growth_v2"},
                }
            ]
        },
    )
    assert update_benefits.status_code == 200

    before_publish = client.get("/api/v1/members/me/tasks", headers=USER_HEADERS)
    assert before_publish.json()["items"][0]["reward_points"] == 10

    publish = client.post("/api/v1/admin/member-config:publish", headers=ADMIN_HEADERS)
    assert publish.status_code == 200
    assert publish.json()["version"] == original_version + 1

    after_publish = client.get("/api/v1/members/me/tasks", headers=USER_HEADERS)
    assert after_publish.json()["items"][0]["reward_points"] == 12

    detail = client.get("/api/v1/admin/members/user-1", headers=ADMIN_HEADERS)
    assert detail.status_code == 200
    assert detail.json()["profile"]["user_id"] == "user-1"


def test_invalid_ledger_query_returns_uniform_error(client) -> None:
    response = client.get(
        "/api/v1/members/me/points/ledger",
        headers=USER_HEADERS,
        params={"change_type": "bad-type"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_change_type"
    assert "request_id" in response.json()


def test_high_frequency_risk_control_blocks_excessive_point_grants(client) -> None:
    tasks = [
        {"task_code": f"task_{index}", "task_type": "manual_action", "title": f"任务{index}"}
        for index in range(6)
    ]
    client.put(
        "/api/v1/admin/member-config/tasks",
        headers=ADMIN_HEADERS,
        json={
            "tasks": [
                {
                    **task,
                    "description": "批量任务",
                    "is_enabled": True,
                    "reward_points": 1,
                    "daily_limit": 1,
                    "window_rule": "daily",
                    "trigger_source": "manual",
                }
                for task in tasks
            ]
        },
    )
    client.post("/api/v1/admin/member-config:publish", headers=ADMIN_HEADERS)

    last_response = None
    for index in range(6):
        last_response = client.post(
            f"/api/v1/members/me/tasks/task_{index}/complete",
            headers={**USER_HEADERS, "x-request-id": f"risk-{index}"},
        )

    assert last_response is not None
    assert last_response.status_code == 429
    assert last_response.json()["error"]["code"] == "risk_control_blocked"
    assert len(store.member_audit_events) >= 5
