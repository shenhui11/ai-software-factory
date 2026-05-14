from __future__ import annotations

import pytest


pytestmark = pytest.mark.anyio

def make_project_payload(genre: str = "fantasy") -> dict[str, object]:
    return {
        "title": "Chronicle",
        "genre": genre,
        "length_type": "long",
        "template_id": "",
        "summary": "Hero rebuilds a broken kingdom.",
        "character_cards": ["Hero", "Rival"],
        "world_rules": ["Magic has a price"],
        "event_summary": ["The city fell in chapter zero"],
        "mode_default": "manual",
    }


<<<<<<< HEAD
def register_and_login(client, username: str, role: str = "creator", password: str = "secret123") -> dict[str, str]:
    client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "role": role},
    )
    logged_in = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    token = logged_in.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_auth_register_login_and_me_flow(client) -> None:
    registered = client.post(
        "/api/auth/register",
        json={"username": "creator1", "password": "secret123", "role": "creator"},
    )
    assert registered.status_code == 200
    assert registered.json()["data"]["username"] == "creator1"

    logged_in = client.post(
        "/api/auth/login",
        json={"username": "creator1", "password": "secret123"},
    )
    assert logged_in.status_code == 200
    token = logged_in.json()["data"]["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["role"] == "creator"


def test_admin_token_can_access_admin_endpoints(client) -> None:
    client.post(
        "/api/auth/register",
        json={"username": "admin1", "password": "secret123", "role": "admin"},
    )
    logged_in = client.post(
        "/api/auth/login",
        json={"username": "admin1", "password": "secret123"},
    )
    token = logged_in.json()["data"]["token"]
    response = client.get("/admin/templates", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_creator_token_cannot_access_admin_endpoints(client) -> None:
    client.post(
        "/api/auth/register",
        json={"username": "creator2", "password": "secret123", "role": "creator"},
    )
    logged_in = client.post(
        "/api/auth/login",
        json={"username": "creator2", "password": "secret123"},
    )
    token = logged_in.json()["data"]["token"]
    response = client.get("/admin/templates", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_register_rejects_duplicate_username(client) -> None:
    first = client.post(
        "/api/auth/register",
        json={"username": "creator_dup", "password": "secret123", "role": "creator"},
    )
    second = client.post(
        "/api/auth/register",
        json={"username": "creator_dup", "password": "secret123", "role": "creator"},
    )
    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["message"] == "用户名已存在"


def test_change_password_rotates_session_and_invalidates_old_token(client) -> None:
    client.post(
        "/api/auth/register",
        json={"username": "creator_pwd", "password": "secret123", "role": "creator"},
    )
    logged_in = client.post(
        "/api/auth/login",
        json={"username": "creator_pwd", "password": "secret123"},
    )
    old_token = logged_in.json()["data"]["token"]

    changed = client.post(
        "/api/auth/password",
        json={"current_password": "secret123", "new_password": "secret456"},
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert changed.status_code == 200
    new_token = changed.json()["data"]["token"]
    assert new_token != old_token

    old_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_me.status_code == 403

    new_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert new_me.status_code == 200

    relogin_old = client.post(
        "/api/auth/login",
        json={"username": "creator_pwd", "password": "secret123"},
    )
    assert relogin_old.status_code == 400

    relogin_new = client.post(
        "/api/auth/login",
        json={"username": "creator_pwd", "password": "secret456"},
    )
    assert relogin_new.status_code == 200


def test_create_project_success(client) -> None:
    headers = register_and_login(client, "creator_projects")
    templates_before = client.get("/api/templates", headers=headers).json()["data"]
    romance_before = next(item for item in templates_before if item["id"] == "tpl-system-romance")
    response = client.post("/api/projects", json=make_project_payload(), headers=headers)
    assert response.status_code == 200
    project = response.json()["data"]
    projects = client.get("/api/projects", headers=headers)
    assert projects.status_code == 200
    assert any(item["id"] == project["id"] for item in projects.json()["data"])
    detail = client.get(f"/api/projects/{project['id']}", headers=headers)
=======
async def test_create_project_success(client) -> None:
    response = await client.post("/api/projects", json=make_project_payload())
    assert response.status_code == 200
    project = response.json()["data"]
    detail = await client.get(f"/api/projects/{project['id']}")
>>>>>>> new-origin/main
    body = detail.json()["data"]
    assert body["project"]["genre"] == "fantasy"
    assert body["project"]["memory"]["character_cards"] == ["Hero", "Rival"]
    assert body["project"]["memory"]["character_profiles"]
    assert body["project"]["memory"]["relationship_states"] == []
    assert body["project"]["memory"]["timeline_nodes"]
    assert body["project"]["memory"]["major_events"]
    templates_after = client.get("/api/templates", headers=headers).json()["data"]
    romance_after = next(item for item in templates_after if item["id"] == "tpl-system-romance")
    assert romance_after["usage_count"] == romance_before["usage_count"] + 1


def test_genre_endpoint_returns_defaults_and_custom_template_genres(client) -> None:
    headers = register_and_login(client, "creator_genres")
    created = client.post(
        "/api/templates",
        json={
            "name": "赛博志怪模板",
            "genre": "cyber_fantasy",
            "style_rules": "强化技术异化。",
            "world_template": "数据城寨",
            "character_template": "异能黑客",
            "outline_template": "异常入侵",
        },
        headers=headers,
    )
    assert created.status_code == 200

    response = client.get("/api/genres")

    assert response.status_code == 200
    genres = response.json()["data"]
    assert any(item["value"] == "fantasy" for item in genres)
    assert any(item["value"] == "cyber_fantasy" for item in genres)


def test_generate_project_foundation_returns_fillable_fields(client) -> None:
    headers = register_and_login(client, "creator_foundation")
    response = client.post(
        "/api/projects/generate-foundation",
        json={
            "title": "星海回声",
            "genre": "sci_fi",
            "length_type": "long",
            "template_id": "tpl-system-romance",
            "summary": "",
            "character_cards": [],
            "world_rules": [],
            "event_summary": [],
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]
    assert data["character_cards"]
    assert data["world_rules"]
    assert data["event_summary"]


def test_create_project_saves_exact_form_values_without_backend_autofill(client) -> None:
    headers = register_and_login(client, "creator_autofill")
    response = client.post(
        "/api/projects",
        json={
            "title": "雾城档案",
            "genre": "suspense",
            "length_type": "long",
            "template_id": "tpl-system-romance",
            "summary": "",
            "character_cards": [],
            "world_rules": [],
            "event_summary": [],
            "mode_default": "manual",
        },
        headers=headers,
    )
    assert response.status_code == 200
    project = response.json()["data"]
    detail = client.get(f"/api/projects/{project['id']}", headers=headers)
    memory = detail.json()["data"]["project"]["memory"]
    assert detail.json()["data"]["project"]["summary"] == ""
    assert memory["character_cards"] == []
    assert memory["character_profiles"] == []
    assert memory["relationship_states"] == []
    assert memory["world_rules"] == []
    assert memory["event_summary"] == []


<<<<<<< HEAD
def test_reject_more_than_ten_chapters(client) -> None:
    headers = register_and_login(client, "creator_limit")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    response = client.post(
=======
async def test_reject_more_than_ten_chapters(client) -> None:
    project = (await client.post("/api/projects", json=make_project_payload())).json()["data"]
    response = await client.post(
>>>>>>> new-origin/main
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 11, "start_chapter_index": 1},
        headers=headers,
    )
    assert response.status_code == 422


<<<<<<< HEAD
def test_auto_flow_returns_three_options_and_highest_selected(client) -> None:
    headers = register_and_login(client, "creator_auto")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    run_result = client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    task_detail = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]
=======
async def test_auto_flow_returns_three_options_and_highest_selected(client) -> None:
    project = (await client.post("/api/projects", json=make_project_payload())).json()["data"]
    task = (
        await client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        )
    ).json()["data"]
    run_result = await client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    task_detail = (await client.get(f"/api/projects/{project['id']}/tasks/{task['id']}")).json()["data"]
>>>>>>> new-origin/main
    assert run_result.status_code == 200
    chapter = task_detail["chapters"][0]
    assert len(chapter["outline_options"]) == 3
    selected = [item for item in chapter["outline_options"] if item["selected"]]
    assert len(selected) == 1
    assert selected[0]["final_score"] == max(item["final_score"] for item in chapter["outline_options"])
    assert chapter["drafts"]
    assert chapter["drafts"][0]["issue_summary"]


<<<<<<< HEAD
def test_manual_mode_waits_for_confirmation_and_can_continue(client) -> None:
    headers = register_and_login(client, "creator_manual")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "manual", "chapter_count": 2, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    waiting = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]
    assert waiting["task"]["status"] == "waiting_user_confirm"
    first_chapter = waiting["chapters"][0]
    confirm = client.post(f"/api/projects/{project['id']}/chapters/{first_chapter['id']}/confirm", headers=headers)
    assert confirm.status_code == 200
    after = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]
    assert len(after["chapters"]) == 2


def test_horror_flow_caps_rewrites_at_five_and_marks_manual_review(client) -> None:
    headers = register_and_login(client, "creator_horror")
    project = client.post("/api/projects", json=make_project_payload(genre="horror"), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    detail = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]
=======
async def test_manual_mode_waits_for_confirmation_and_can_continue(client) -> None:
    project = (await client.post("/api/projects", json=make_project_payload())).json()["data"]
    task = (
        await client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"mode": "manual", "chapter_count": 2, "start_chapter_index": 1},
        )
    ).json()["data"]
    await client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    waiting = (await client.get(f"/api/projects/{project['id']}/tasks/{task['id']}")).json()["data"]
    assert waiting["task"]["status"] == "waiting_user_confirm"
    first_chapter = waiting["chapters"][0]
    confirm = await client.post(f"/api/projects/{project['id']}/chapters/{first_chapter['id']}/confirm")
    assert confirm.status_code == 200
    after = (await client.get(f"/api/projects/{project['id']}/tasks/{task['id']}")).json()["data"]
    assert len(after["chapters"]) == 2


async def test_horror_flow_caps_rewrites_at_five_and_marks_manual_review(client) -> None:
    project = (await client.post("/api/projects", json=make_project_payload(genre="horror"))).json()["data"]
    task = (
        await client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        )
    ).json()["data"]
    await client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    detail = (await client.get(f"/api/projects/{project['id']}/tasks/{task['id']}")).json()["data"]
>>>>>>> new-origin/main
    chapter = detail["chapters"][0]
    drafts = chapter["drafts"]
    assert len(drafts) == 6
    assert chapter["rewrite_count"] == 5
    assert chapter["needs_manual_review"] is True
    selected = [draft for draft in drafts if draft["selected"]][0]
    assert selected["final_score"] == max(draft["final_score"] for draft in drafts)


<<<<<<< HEAD
def test_chapter_rewrite_and_expand_return_diff(client) -> None:
    headers = register_and_login(client, "creator_rewrite")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    chapter = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]["chapters"][0]
    draft = [item for item in chapter["drafts"] if item["selected"]][0]
    rewrite = client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/rewrite",
        json={"instruction": "Tighten the pacing", "chapter_content": draft["content"]},
        headers=headers,
    )
    expand = client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/expand",
        json={"instruction": "Add more sensory detail", "chapter_content": draft["content"]},
        headers=headers,
=======
async def test_paragraph_rewrite_and_expand_return_diff(client) -> None:
    project = (await client.post("/api/projects", json=make_project_payload())).json()["data"]
    task = (
        await client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        )
    ).json()["data"]
    await client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    chapter = (
        await client.get(f"/api/projects/{project['id']}/tasks/{task['id']}")
    ).json()["data"]["chapters"][0]
    draft = [item for item in chapter["drafts"] if item["selected"]][0]
    rewrite = await client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/paragraph-rewrite",
        json={"paragraph": draft["content"], "instruction": "Tighten the pacing"},
    )
    expand = await client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/paragraph-expand",
        json={"paragraph": draft["content"], "instruction": "Add more sensory detail"},
>>>>>>> new-origin/main
    )
    assert rewrite.status_code == 200
    assert expand.status_code == 200
    assert rewrite.json()["data"]["diff"]
    assert expand.json()["data"]["diff"]
    assert expand.json()["data"]["chapter_updated"]


<<<<<<< HEAD
def test_chapter_paragraph_rewrite_and_expand_return_diff(client) -> None:
    headers = register_and_login(client, "creator_para_rewrite")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    chapter = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]["chapters"][0]
    paragraph = "第一段\n第二段"
    rewrite = client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/rewrite",
        json={"instruction": "精炼第一段", "chapter_content": paragraph, "paragraph": "第一段"},
        headers=headers,
    )
    expand = client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/expand",
        json={"instruction": "扩写第二段", "chapter_content": paragraph, "paragraph": "第二段"},
        headers=headers,
    )
    assert rewrite.status_code == 200
    assert expand.status_code == 200
    assert rewrite.json()["data"]["chapter_updated"]
    assert expand.json()["data"]["chapter_updated"]


def test_chapter_paragraph_remove_return_diff(client) -> None:
    headers = register_and_login(client, "creator_remove")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    chapter = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]["chapters"][0]
    remove = client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/remove",
        json={"instruction": "删除重复铺垫", "chapter_content": "第一段\n第二段", "paragraph": "第一段"},
        headers=headers,
    )

    assert remove.status_code == 200
    assert remove.json()["data"]["chapter_updated"] == "第二段"
    assert any(item["type"] == "removed" for item in remove.json()["data"]["diff"])


def test_generated_chapter_updates_structured_memory_fields(client) -> None:
    headers = register_and_login(client, "creator_memory")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    detail = client.get(f"/api/projects/{project['id']}", headers=headers)

    assert detail.status_code == 200
    memory = detail.json()["data"]["project"]["memory"]
    assert memory["latest_chapter_index"] == 1
    assert memory["character_profiles"]
    assert memory["chapter_summaries"]
    assert memory["relationship_states"]
    assert any(item["chapter_index"] == 1 for item in memory["timeline_nodes"])
    assert any(item["chapter_index"] == 1 for item in memory["major_events"])
    assert memory["foreshadow_threads"]
    assert memory["fact_records"]


def test_chapter_title_can_be_updated_before_confirmation(client) -> None:
    headers = register_and_login(client, "creator_title")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "manual", "chapter_count": 1, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    chapter = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]["chapters"][0]

    updated = client.patch(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}",
        json={"title": "月蚀档案馆的来信"},
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["data"]["title"] == "月蚀档案馆的来信"


def test_admin_and_compliance_endpoints_return_data(client, admin_headers) -> None:
    project = client.post("/api/projects", json=make_project_payload()).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    assert client.get("/admin/templates", headers=admin_headers).status_code == 200
    assert client.get("/admin/memberships", headers=admin_headers).status_code == 200
    assert client.get("/admin/orders", headers=admin_headers).status_code == 200
    assert client.get("/admin/safety/policies", headers=admin_headers).status_code == 200
    logs = client.get("/admin/logs/tasks", headers=admin_headers)
=======
async def test_admin_and_compliance_endpoints_return_data(client) -> None:
    project = (await client.post("/api/projects", json=make_project_payload())).json()["data"]
    task = (
        await client.post(
            f"/api/projects/{project['id']}/chapters/generate",
            json={"mode": "auto", "chapter_count": 1, "start_chapter_index": 1},
        )
    ).json()["data"]
    await client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run")
    assert (await client.get("/admin/templates")).status_code == 200
    assert (await client.get("/admin/memberships")).status_code == 200
    assert (await client.get("/admin/orders")).status_code == 200
    assert (await client.get("/admin/safety/policies")).status_code == 200
    logs = await client.get("/admin/logs/tasks")
>>>>>>> new-origin/main
    assert logs.status_code == 200
    assert logs.json()["data"]


<<<<<<< HEAD
def test_template_management_and_quota_adjustment(client, admin_headers) -> None:
    headers = register_and_login(client, "creator_template_mgmt")
    created = client.post(
        "/api/templates",
        json={
            "name": "测试模板",
            "genre": "fantasy",
            "tags": ["冒险", "成长"],
            "style_rules": "强化冲突与节奏。",
            "world_template": "废墟王都",
            "character_template": "主角、宿敌",
            "outline_template": "发现、对抗、揭露",
        },
        headers=headers,
    )
    assert created.status_code == 200
    template = created.json()["data"]

    updated = client.patch(
        f"/api/templates/{template['id']}",
        json={"name": "测试模板-已更新", "style_rules": "强化冲突、节奏与悬念。", "tags": ["冒险", "升级"]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "测试模板-已更新"
    assert updated.json()["data"]["tags"] == ["冒险", "升级"]

    published = client.post(f"/admin/templates/{template['id']}/publish", headers=admin_headers)
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "published"

    adjusted = client.post(
        "/admin/quotas/adjust",
        json={"free_delta": 2, "monthly_delta": 3},
        headers=admin_headers,
    )
    assert adjusted.status_code == 200
    assert adjusted.json()["data"]["free_remaining"] >= 7
    assert adjusted.json()["data"]["monthly_remaining"] >= 23


def test_admin_can_manage_membership_plans_and_orders(client, admin_headers) -> None:
    created_plan = client.post(
        "/admin/memberships/plans",
        json={
            "name": "高阶套餐",
            "free_chapter_quota": 12,
            "monthly_quota": 66,
            "description": "适合高频连载作者。",
        },
        headers=admin_headers,
    )
    assert created_plan.status_code == 200
    plan = created_plan.json()["data"]

    updated_plan = client.patch(
        f"/admin/memberships/plans/{plan['id']}",
        json={
            "name": "高阶套餐 Pro",
            "free_chapter_quota": 15,
            "monthly_quota": 80,
            "description": "升级后的高频连载套餐。",
        },
        headers=admin_headers,
    )
    assert updated_plan.status_code == 200
    assert updated_plan.json()["data"]["monthly_quota"] == 80

    activated_plan = client.post(
        f"/admin/memberships/plans/{plan['id']}/activate",
        headers=admin_headers,
    )
    assert activated_plan.status_code == 200

    memberships = client.get("/admin/memberships", headers=admin_headers)
    assert memberships.status_code == 200
    assert memberships.json()["data"]["active_plan_id"] == plan["id"]

    created_order = client.post(
        "/admin/orders",
        json={
            "plan_id": plan["id"],
            "amount": 29.9,
            "status": "待支付",
            "note": "首单测试",
        },
        headers=admin_headers,
    )
    assert created_order.status_code == 200
    order = created_order.json()["data"]

    updated_order = client.patch(
        f"/admin/orders/{order['id']}",
        json={
            "plan_id": plan["id"],
            "amount": 29.9,
            "status": "已支付",
            "note": "财务已确认到账",
        },
        headers=admin_headers,
    )
    assert updated_order.status_code == 200
    assert updated_order.json()["data"]["status"] == "已支付"
    assert updated_order.json()["data"]["note"] == "财务已确认到账"


def test_non_admin_cannot_access_admin_endpoints(client) -> None:
    assert client.get("/admin/templates").status_code == 403
    assert client.get("/admin/memberships").status_code == 403
    assert client.post("/admin/quotas/adjust", json={"free_delta": 1, "monthly_delta": 1}).status_code == 403

    body = client.get("/admin/templates").json()
    assert body["code"] == "FORBIDDEN"


def test_projects_are_isolated_by_user(client) -> None:
    alice_headers = register_and_login(client, "creator_alice")
    bob_headers = register_and_login(client, "creator_bob")

    alice_project = client.post("/api/projects", json=make_project_payload(), headers=alice_headers).json()["data"]

    alice_projects = client.get("/api/projects", headers=alice_headers)
    bob_projects = client.get("/api/projects", headers=bob_headers)
    assert any(item["id"] == alice_project["id"] for item in alice_projects.json()["data"])
    assert all(item["id"] != alice_project["id"] for item in bob_projects.json()["data"])

    bob_detail = client.get(f"/api/projects/{alice_project['id']}", headers=bob_headers)
    assert bob_detail.status_code == 403


def test_user_templates_and_quota_are_isolated_by_user(client) -> None:
    alice_headers = register_and_login(client, "creator_tpl_alice")
    bob_headers = register_and_login(client, "creator_tpl_bob")

    created = client.post(
        "/api/templates",
        json={
            "name": "Alice 模板",
            "genre": "fantasy",
            "tags": ["冒险"],
            "style_rules": "强化冲突。",
            "world_template": "古堡",
            "character_template": "主角",
            "outline_template": "发现异常",
        },
        headers=alice_headers,
    )
    assert created.status_code == 200
    template_id = created.json()["data"]["id"]

    alice_templates = client.get("/api/templates", headers=alice_headers).json()["data"]
    bob_templates = client.get("/api/templates", headers=bob_headers).json()["data"]
    assert any(item["id"] == template_id for item in alice_templates)
    assert all(item["id"] != template_id for item in bob_templates)
    alice_quota = client.get("/api/membership/quotas", headers=alice_headers).json()["data"]["quota"]
    bob_quota = client.get("/api/membership/quotas", headers=bob_headers).json()["data"]["quota"]
    assert alice_quota == bob_quota


def test_admin_can_view_and_adjust_target_user_quota(client, admin_headers) -> None:
    creator_headers = register_and_login(client, "creator_target_quota")
    me = client.get("/api/auth/me", headers=creator_headers).json()["data"]
    user_id = me["id"]

    before = client.get(f"/admin/memberships?target_user_id={user_id}", headers=admin_headers)
    assert before.status_code == 200
    assert before.json()["data"]["target_user_id"] == user_id

    adjusted = client.post(
        "/admin/quotas/adjust",
        json={"target_user_id": user_id, "free_delta": 4, "monthly_delta": 1},
        headers=admin_headers,
    )
    assert adjusted.status_code == 200
    assert adjusted.json()["data"]["free_remaining"] >= 9

    creator_quota = client.get("/api/membership/quotas", headers=creator_headers)
    assert creator_quota.status_code == 200
    assert creator_quota.json()["data"]["quota"]["free_remaining"] >= 9


def test_admin_can_adjust_target_user_quota_by_username(client, admin_headers) -> None:
    creator_headers = register_and_login(client, "18855115138")

    adjusted = client.post(
        "/admin/quotas/adjust",
        json={"target_user_id": "18855115138", "free_delta": 3, "monthly_delta": 2},
        headers=admin_headers,
    )
    assert adjusted.status_code == 200

    creator_quota = client.get("/api/membership/quotas", headers=creator_headers)
    assert creator_quota.status_code == 200
    quota = creator_quota.json()["data"]["quota"]
    assert quota["free_remaining"] >= 8
    assert quota["monthly_remaining"] >= 22


def test_quota_alias_is_migrated_from_username_to_user_id(client, admin_headers) -> None:
    creator_headers = register_and_login(client, "18855115138")
    creator_me = client.get("/api/auth/me", headers=creator_headers).json()["data"]
    assert creator_me["id"] != "18855115138"

    client.post(
        "/admin/quotas/adjust",
        json={"target_user_id": "18855115138", "free_delta": 6, "monthly_delta": 4},
        headers=admin_headers,
    )

    creator_quota = client.get("/api/membership/quotas", headers=creator_headers)
    assert creator_quota.status_code == 200
    quota = creator_quota.json()["data"]["quota"]
    assert quota["free_remaining"] >= 11
    assert quota["monthly_remaining"] >= 24


def test_admin_can_list_users_for_quota_operations(client, admin_headers) -> None:
    creator_headers = register_and_login(client, "creator_quota_list")
    creator_me = client.get("/api/auth/me", headers=creator_headers).json()["data"]

    response = client.get("/admin/users", headers=admin_headers)

    assert response.status_code == 200
    users = response.json()["data"]
    assert any(user["id"] == creator_me["id"] and user["username"] == "creator_quota_list" for user in users)


def test_admin_can_create_creator_and_reset_password(client, admin_headers) -> None:
    created = client.post(
        "/admin/users",
        json={"username": "managed_creator", "password": "11111111", "role": "creator"},
        headers=admin_headers,
    )
    assert created.status_code == 200
    user = created.json()["data"]
    assert user["username"] == "managed_creator"
    assert user["role"] == "creator"

    login_before = client.post(
        "/api/auth/login",
        json={"username": "managed_creator", "password": "11111111"},
    )
    assert login_before.status_code == 200

    reset = client.post(f"/admin/users/{user['id']}/reset-password", headers=admin_headers)
    assert reset.status_code == 200
    assert reset.json()["data"]["reset_password"] == "11111111"

    login_after = client.post(
        "/api/auth/login",
        json={"username": "managed_creator", "password": "11111111"},
    )
    assert login_after.status_code == 200


def test_chapter_outline_and_draft_can_be_updated_before_confirmation(client) -> None:
    headers = register_and_login(client, "creator_outline_edit")
    project = client.post("/api/projects", json=make_project_payload(), headers=headers).json()["data"]
    task = client.post(
        f"/api/projects/{project['id']}/chapters/generate",
        json={"mode": "manual", "chapter_count": 1, "start_chapter_index": 1},
        headers=headers,
    ).json()["data"]
    client.post(f"/api/projects/{project['id']}/tasks/{task['id']}/run", headers=headers)
    detail = client.get(f"/api/projects/{project['id']}/tasks/{task['id']}", headers=headers).json()["data"]
    chapter = detail["chapters"][0]
    option = chapter["outline_options"][0]
    selected_draft = next(draft for draft in chapter["drafts"] if draft["selected"])

    select_response = client.post(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/outlines/{option['id']}/select",
        headers=headers,
    )
    assert select_response.status_code == 200
    updated_chapter = select_response.json()["data"]
    assert any(item["selected"] and item["id"] == option["id"] for item in updated_chapter["outline_options"])

    outline_update = client.patch(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/outlines/{option['id']}",
        json={
            "content": "人工调整后的章节走向",
            "core_conflict": "人工调整后的核心冲突",
            "key_event": "人工调整后的关键事件",
            "ending_hook": "人工调整后的结尾钩子",
        },
        headers=headers,
    )
    assert outline_update.status_code == 200
    assert outline_update.json()["data"]["outline_options"][0]["content"] == "人工调整后的章节走向"

    draft_update = client.patch(
        f"/api/projects/{project['id']}/chapters/{chapter['id']}/drafts/{selected_draft['id']}",
        json={"content": "人工修改后的章节正文"},
        headers=headers,
    )
    assert draft_update.status_code == 200
    chapter_after_draft = draft_update.json()["data"]
    selected_after_draft = next(draft for draft in chapter_after_draft["drafts"] if draft["selected"])
    assert selected_after_draft["content"] == "人工修改后的章节正文"


def test_blocked_content_returns_structured_error(client) -> None:
    response = client.post(
=======
async def test_blocked_content_returns_structured_error(client) -> None:
    response = await client.post(
>>>>>>> new-origin/main
        "/api/projects",
        json={**make_project_payload(), "summary": "一场禁忌仪式由此开始。"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "CONTENT_BLOCKED"
    assert body["request_id"].startswith("req_")
