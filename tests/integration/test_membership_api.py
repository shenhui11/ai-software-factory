from __future__ import annotations


def test_unauthorized_requests_return_uniform_error(client) -> None:
    response = client.get("/api/v1/members/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert "request_id" in body


def test_member_profile_and_dashboard(client, user_headers) -> None:
    member = client.get("/api/v1/members/me", headers=user_headers)
    dashboard = client.get("/api/v1/members/me/dashboard", headers=user_headers)
    tasks = client.get("/api/v1/members/me/tasks", headers=user_headers)

    assert member.status_code == 200
    assert dashboard.status_code == 200
    assert tasks.status_code == 200
    assert member.json()["membership_status"] == "regular"
    assert dashboard.json()["points_balance"] == member.json()["points_balance"]
    assert tasks.json()["items"]


def test_check_in_is_recorded_once_with_ledger(client, user_headers) -> None:
    first = client.post(
        "/api/v1/members/me/check-ins",
        headers={**user_headers, "X-Request-Id": "check-1"},
    )
    second = client.post(
        "/api/v1/members/me/check-ins",
        headers={**user_headers, "X-Request-Id": "check-2"},
    )
    ledger = client.get("/api/v1/members/me/points/ledger", headers=user_headers)

    assert first.status_code == 200
    assert second.status_code == 409
    items = ledger.json()["items"]
    assert len(items) == 1
    assert items[0]["source_type"] == "check_in"


def test_same_request_id_is_idempotent_for_task_completion(client, user_headers) -> None:
    first = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers={**user_headers, "X-Request-Id": "same-task"},
    )
    second = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers={**user_headers, "X-Request-Id": "same-task"},
    )
    ledger = client.get("/api/v1/members/me/points/ledger", headers=user_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["granted_points"] == 0
    assert len(ledger.json()["items"]) == 1


def test_admin_permissions_are_enforced(client, user_headers, admin_headers) -> None:
    forbidden = client.get("/api/v1/admin/member-config", headers=user_headers)
    allowed = client.get("/api/v1/admin/member-config", headers=admin_headers)

    assert forbidden.status_code == 403
    assert allowed.status_code == 200


def test_unpublished_config_does_not_change_user_view(client, user_headers, admin_headers) -> None:
    before = client.get("/api/v1/members/me/tasks", headers=user_headers).json()["items"]
    response = client.put(
        "/api/v1/admin/member-config/tasks",
        headers={**admin_headers, "X-Request-Id": "draft-update"},
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
                    "reward_points": 88,
                    "daily_limit": 1,
                    "is_enabled": True,
                },
            ]
        },
    )
    after = client.get("/api/v1/members/me/tasks", headers=user_headers).json()["items"]

    assert response.status_code == 200
    assert before == after


def test_invalid_publish_returns_uniform_error(client, admin_headers) -> None:
    client.put(
        "/api/v1/admin/member-config/levels",
        headers={**admin_headers, "X-Request-Id": "bad-levels"},
        json={
            "levels": [
                {
                    "level_code": "L2",
                    "level_name": "Growth",
                    "growth_threshold": 10,
                    "description": "growth",
                },
                {
                    "level_code": "L2",
                    "level_name": "Duplicate",
                    "growth_threshold": 5,
                    "description": "dup",
                },
            ]
        },
    )
    response = client.post(
        "/api/v1/admin/member-config:publish",
        headers={**admin_headers, "X-Request-Id": "bad-publish"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "config_validation_failed"
    assert body["request_id"] == "bad-publish"
