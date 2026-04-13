from __future__ import annotations

from apps.backend.infrastructure.member_store import member_store


def auth_headers(
    user_id: str = "user-1",
    role: str = "user",
    request_id: str | None = None,
) -> dict[str, str]:
    headers = {"X-User-Id": user_id, "X-Role": role}
    if request_id is not None:
        headers["X-Request-Id"] = request_id
    return headers


def test_get_member_profile_initializes_account_and_status(client):
    response = client.get("/api/v1/members/me", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["membership_status"] == "regular"
    assert body["current_level"] == 1
    assert body["points_balance"] == 0


def test_dashboard_returns_tasks_benefits_and_rewards(client):
    client.post("/api/v1/members/me/check-ins", headers=auth_headers())
    response = client.get("/api/v1/members/me/dashboard", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert "tasks" in body
    assert "recent_rewards" in body
    assert body["points_earned_total"] == 10


def test_tasks_list_uses_published_config(client):
    response = client.get("/api/v1/members/me/tasks", headers=auth_headers())
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["task_code"] == "daily_check_in"
    assert item["reward_points"] == 10


def test_check_in_grants_points_and_writes_ledger(client):
    response = client.post("/api/v1/members/me/check-ins", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["granted_points"] == 10
    ledger = client.get("/api/v1/members/me/points/ledger", headers=auth_headers()).json()
    assert ledger["items"][0]["source_type"] == "check_in"


def test_complete_task_writes_task_completion_ledger(client):
    response = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers=auth_headers(request_id="req-1"),
    )
    assert response.status_code == 200
    assert response.json()["reward_result"]["reward_code"] == "complete_profile"
    ledger = client.get(
        "/api/v1/members/me/points/ledger",
        headers=auth_headers(),
        params={"change_type": "earn"},
    )
    assert ledger.status_code == 200
    assert ledger.json()["items"][0]["source_type"] == "task_completion"


def test_level_up_unlocks_benefit_and_reward_record(client):
    client.post("/api/v1/members/me/check-ins", headers=auth_headers(request_id="req-a"))
    response = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers=auth_headers(request_id="req-b"),
    )
    assert response.status_code == 200
    assert response.json()["level_up"] is True
    profile = client.get("/api/v1/members/me", headers=auth_headers()).json()
    assert profile["membership_status"] == "growth_member"
    assert profile["unlocked_benefits"][0]["benefit_code"] == "priority_badge"
    rewards = client.get("/api/v1/members/me/rewards", headers=auth_headers()).json()
    assert len(rewards["items"]) >= 2


def test_duplicate_check_in_is_blocked_without_extra_ledger(client):
    first = client.post("/api/v1/members/me/check-ins", headers=auth_headers())
    second = client.post("/api/v1/members/me/check-ins", headers=auth_headers())
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "daily_limit_reached"
    ledger = client.get("/api/v1/members/me/points/ledger", headers=auth_headers()).json()
    assert len(ledger["items"]) == 1


def test_duplicate_request_id_does_not_double_count_task(client):
    first = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers=auth_headers(request_id="same-id"),
    )
    second = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers=auth_headers(request_id="same-id"),
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_request"
    ledger = client.get("/api/v1/members/me/points/ledger", headers=auth_headers()).json()
    assert len(ledger["items"]) == 1


def test_disabled_task_cannot_be_completed(client):
    client.put(
        "/api/v1/admin/member-config/tasks",
        headers=auth_headers("admin-1", "admin"),
        json={
            "tasks": [
                {
                    "task_code": "complete_profile",
                    "title": "Complete Profile",
                    "task_type": "action",
                    "reward_points": 20,
                    "enabled": False,
                    "daily_limit": 1,
                }
            ]
        },
    )
    client.post(
        "/api/v1/admin/member-config:publish",
        headers=auth_headers("admin-1", "admin"),
    )
    response = client.post(
        "/api/v1/members/me/tasks/complete_profile/complete",
        headers=auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "task_not_available"


def test_admin_can_update_and_publish_config(client):
    config_before = client.get(
        "/api/v1/admin/member-config",
        headers=auth_headers("admin-1", "admin"),
    )
    assert config_before.status_code == 200
    task_update = client.put(
        "/api/v1/admin/member-config/tasks",
        headers=auth_headers("admin-1", "admin"),
        json={
            "tasks": [
                {
                    "task_code": "watch_demo",
                    "title": "Watch Demo",
                    "task_type": "action",
                    "reward_points": 15,
                    "enabled": True,
                    "daily_limit": 1,
                }
            ]
        },
    )
    assert task_update.status_code == 200
    publish = client.post(
        "/api/v1/admin/member-config:publish",
        headers=auth_headers("admin-1", "admin"),
    )
    assert publish.status_code == 200
    tasks = client.get("/api/v1/members/me/tasks", headers=auth_headers()).json()["items"]
    assert tasks[0]["task_code"] == "watch_demo"


def test_non_admin_cannot_access_admin_routes(client):
    response = client.get("/api/v1/admin/member-config", headers=auth_headers())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_unauthenticated_request_uses_uniform_error(client):
    response = client.get("/api/v1/members/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"
    assert "request_id" in response.json()


def test_invalid_ledger_query_returns_uniform_error(client):
    response = client.get(
        "/api/v1/members/me/points/ledger",
        headers=auth_headers(),
        params={"change_type": "bad", "cursor": "x", "limit": 500},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] in {
        "invalid_change_type",
        "invalid_cursor",
        "invalid_limit",
    }


def test_admin_member_detail_returns_member_and_ledger(client):
    client.post("/api/v1/members/me/check-ins", headers=auth_headers())
    response = client.get(
        "/api/v1/admin/members/user-1",
        headers=auth_headers("admin-1", "admin"),
    )
    assert response.status_code == 200
    assert response.json()["member"]["points_balance"] == 10
    assert len(response.json()["ledger"]) == 1


def test_member_events_are_recorded_for_core_actions(client):
    client.post("/api/v1/members/me/check-ins", headers=auth_headers(request_id="evt-1"))
    assert any(event.event_type == "points_granted" for event in member_store.member_events)
    assert any(event.event_type == "reward_dispatched" for event in member_store.member_events)
