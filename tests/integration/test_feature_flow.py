from __future__ import annotations


def make_project_payload(genre: str = "fantasy") -> dict[str, object]:
    return {
        "title": "Chronicle",
        "genre": genre,
        "length_type": "long",
        "template_id": "tpl-system-romance",
        "summary": "Hero rebuilds a broken kingdom.",
        "character_cards": ["Hero", "Rival"],
        "world_rules": ["Magic has a price"],
        "event_summary": ["The city fell in chapter zero"],
        "mode_default": "manual",
    }


def test_create_project_success(client) -> None:
    response = client.post("/api/projects", json=make_project_payload())
    assert response.status_code == 200
    project = response.json()["data"]
    detail = client.get(f"/api/projects/{project['id']}")
    body = detail.json()["data"]
    assert body["project"]["genre"] == "fantasy"
    assert body["project"]["memory"]["character_cards"] == ["Hero", "Rival"]


def test_reject_more_than_ten_chapters(client) -> None:
    project = client.post("/api/projects", json=make_project_payload()).json()["data"]
    response = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 11, "start_chapter_index": 1},
    )
    assert response.status_code == 422


def test_auto_flow_returns_three_options_and_highest_selected(client) -> None:
    project = client.post("/api/projects", json=make_project_payload()).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
    ).json()["data"]
    run_result = client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    task_detail = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}").json()["data"]
    assert run_result.status_code == 200
    chapter = task_detail["chapters"][0]
    assert len(chapter["outline_options"]) == 3
    selected = [item for item in chapter["outline_options"] if item["selected"]]
    assert len(selected) == 1
    assert selected[0]["final_score"] == max(item["final_score"] for item in chapter["outline_options"])
    assert chapter["drafts"]
    assert chapter["drafts"][0]["issue_summary"]


def test_manual_mode_waits_for_confirmation_and_can_continue(client) -> None:
    project = client.post("/api/projects", json=make_project_payload()).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "manual", "chapter_count": 2, "start_chapter_index": 1},
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    waiting = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}").json()["data"]
    assert waiting["task"]["status"] == "waiting_user_confirm"
    first_chapter = waiting["chapters"][0]
    confirm = client.post(f"/api/projects/{project['id']}/chapters/{first_chapter['id']}/confirm")
    assert confirm.status_code == 200
    after = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}").json()["data"]
    assert len(after["chapters"]) == 2


def test_horror_flow_caps_rewrites_at_five_and_marks_manual_review(client) -> None:
    project = client.post("/api/projects", json=make_project_payload(genre="horror")).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    detail = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}").json()["data"]
    chapter = detail["chapters"][0]
    drafts = chapter["drafts"]
    assert len(drafts) == 6
    assert chapter["rewrite_count"] == 5
    assert chapter["needs_manual_review"] is True
    selected = [draft for draft in drafts if draft["selected"]][0]
    assert selected["final_score"] == max(draft["final_score"] for draft in drafts)


def test_paragraph_rewrite_and_expand_return_diff(client) -> None:
    project = client.post("/api/projects", json=make_project_payload()).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    chapter = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}").json()["data"]["chapters"][0]
    draft = [item for item in chapter["drafts"] if item["selected"]][0]
    rewrite = client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/paragraph-rewrite",
        json={"paragraph": draft["content"], "instruction": "Tighten the pacing"},
    )
    expand = client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/paragraph-expand",
        json={"paragraph": draft["content"], "instruction": "Add more sensory detail"},
    )
    assert rewrite.status_code == 200
    assert expand.status_code == 200
    assert rewrite.json()["data"]["diff"]
    assert expand.json()["data"]["diff"]


def test_admin_and_compliance_endpoints_return_data(client) -> None:
    project = client.post("/api/projects", json=make_project_payload()).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    assert client.get("/admin/templates").status_code == 200
    assert client.get("/admin/memberships").status_code == 200
    assert client.get("/admin/orders").status_code == 200
    assert client.get("/admin/safety/policies").status_code == 200
    logs = client.get("/admin/logs/tasks")
    assert logs.status_code == 200
    assert logs.json()["data"]


def test_blocked_content_returns_structured_error(client) -> None:
    response = client.post(
        "/api/projects",
        json={**make_project_payload(), "summary": "A forbidden ritual starts here."},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "CONTENT_BLOCKED"
    assert body["request_id"].startswith("req_")
