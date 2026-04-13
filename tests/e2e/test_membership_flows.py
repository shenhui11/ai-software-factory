from __future__ import annotations


def publish_growth_config(client, admin_headers) -> None:
    client.put(
        "/api/v1/admin/member-config/tasks",
        headers={**admin_headers, "X-Request-Id": "cfg-task"},
        json={
            "tasks": [
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
                    "reward_points": 30,
                    "daily_limit": 1,
                    "is_enabled": True,
                },
            ]
        },
    )
    client.put(
        "/api/v1/admin/member-config/levels",
        headers={**admin_headers, "X-Request-Id": "cfg-level"},
        json={
            "levels": [
                {
                    "level_code": "L1",
                    "level_name": "Regular",
                    "growth_threshold": 0,
                    "description": "base",
                },
                {
                    "level_code": "L2",
                    "level_name": "Growth Member",
                    "growth_threshold": 40,
                    "description": "member",
                },
            ]
        },
    )
    client.put(
        "/api/v1/admin/member-config/benefits",
        headers={**admin_headers, "X-Request-Id": "cfg-benefit"},
        json={
            "benefits": [
                {
                    "benefit_code": "member_badge",
                    "title": "Growth Member Badge",
                    "description": "Visible member badge",
                    "is_enabled": True,
                }
            ],
            "mappings": [{"level_code": "L2", "benefit_codes": ["member_badge"]}],
        },
    )
    publish = client.post(
        "/api/v1/admin/member-config:publish",
        headers={**admin_headers, "X-Request-Id": "cfg-publish"},
    )
    assert publish.status_code == 200


def test_growth_member_end_to_end(client, user_headers, admin_headers) -> None:
    publish_growth_config(client, admin_headers)

    check_in = client.post(
        "/api/v1/members/me/check-ins",
        headers={**user_headers, "X-Request-Id": "user-check"},
    )
    task = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers={**user_headers, "X-Request-Id": "user-task"},
    )
    member = client.get("/api/v1/members/me", headers=user_headers)
    dashboard = client.get("/api/v1/members/me/dashboard", headers=user_headers)
    ledger = client.get("/api/v1/members/me/points/ledger", headers=user_headers)
    rewards = client.get("/api/v1/members/me/rewards", headers=user_headers)

    assert check_in.status_code == 200
    assert task.status_code == 200
    assert task.json()["level_up"] is True
    assert member.json()["membership_status"] == "growth_member"
    assert member.json()["current_level"] == "L2"
    assert dashboard.json()["unlocked_benefits"][0]["benefit_code"] == "member_badge"
    assert len(ledger.json()["items"]) == 2
    assert rewards.json()["items"][0]["reward_code"] == "member_badge"


def test_admin_publish_changes_user_task_view(client, user_headers, admin_headers) -> None:
    before = client.get("/api/v1/members/me/tasks", headers=user_headers)
    client.put(
        "/api/v1/admin/member-config/tasks",
        headers={**admin_headers, "X-Request-Id": "cfg-task-2"},
        json={
            "tasks": [
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
                    "reward_points": 55,
                    "daily_limit": 1,
                    "is_enabled": True,
                },
            ]
        },
    )
    client.post(
        "/api/v1/admin/member-config:publish",
        headers={**admin_headers, "X-Request-Id": "cfg-publish-2"},
    )
    after = client.get("/api/v1/members/me/tasks", headers=user_headers)
    updated = {item["task_code"]: item["reward_points"] for item in after.json()["items"]}

    assert before.status_code == 200
    assert after.status_code == 200
    assert updated["complete_profile"] == 55


def test_risk_control_and_admin_member_lookup(client, user_headers, admin_headers) -> None:
    publish_growth_config(client, admin_headers)
    first = client.post(
        "/api/v1/members/me/check-ins",
        headers={**user_headers, "X-Request-Id": "risk-1"},
    )
    second = client.post(
        "/api/v1/members/me/check-ins",
        headers={**user_headers, "X-Request-Id": "risk-2"},
    )
    third = client.post(
        "/api/v1/members/me/check-ins",
        headers={**user_headers, "X-Request-Id": "risk-3"},
    )
    blocked = client.post(
        "/api/v1/members/me/check-ins",
        headers={**user_headers, "X-Request-Id": "risk-4"},
    )
    details = client.get("/api/v1/admin/members/user-1", headers=admin_headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert third.status_code == 409
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "risk_control_blocked"
    assert details.status_code == 200
    assert "member" in details.json()
