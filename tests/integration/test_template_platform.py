from __future__ import annotations

from apps.backend.infrastructure.store import store

ADMIN_HEADERS = {"x-user-id": "admin-1", "x-user-role": "admin"}
USER_HEADERS = {"x-user-id": "user-1", "x-user-role": "user"}
OTHER_USER_HEADERS = {"x-user-id": "user-2", "x-user-role": "user"}


def create_taxonomy(client) -> tuple[str, str]:
    category_response = client.post(
        "/api/v1/admin/template-categories",
        headers={"x-user-role": "admin"},
        json={
            "name": "运营",
            "description": "运营模板",
            "sort_order": 1,
            "is_active": True,
        },
    )
    assert category_response.status_code == 200
    tag_response = client.post(
        "/api/v1/admin/template-tags",
        headers={"x-user-role": "admin"},
        json={"name": "活动", "description": "活动模板", "is_active": True},
    )
    assert tag_response.status_code == 200
    return category_response.json()["id"], tag_response.json()["id"]


def create_system_template(client, category_id: str, tag_id: str, content: str = "模板正文") -> dict[str, object]:
    response = client.post(
        "/api/v1/admin/templates",
        headers=ADMIN_HEADERS,
        json={
            "name": "系统活动模板",
            "description": "用于活动策划",
            "content": content,
            "category_id": category_id,
            "tag_ids": [tag_id],
            "status": "draft",
        },
    )
    assert response.status_code == 200
    return response.json()


def publish_template(client, template_id: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/admin/templates/{template_id}:publish",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    return response.json()


def test_admin_can_manage_and_filter_system_templates(client):
    category_id, tag_id = create_taxonomy(client)
    first = create_system_template(client, category_id, tag_id)
    publish_template(client, first["id"])
    second = client.post(
        "/api/v1/admin/templates",
        headers=ADMIN_HEADERS,
        json={
            "name": "草稿模板",
            "description": "仅草稿",
            "content": "",
            "category_id": category_id,
            "tag_ids": [tag_id],
            "status": "draft",
        },
    ).json()

    response = client.get(
        "/api/v1/admin/templates",
        headers={"x-user-role": "admin"},
        params={"status": "published", "category_id": category_id, "keyword": "活动", "tag_id": tag_id},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == first["id"]

    offline_response = client.post(
        f"/api/v1/admin/templates/{first['id']}:offline",
        headers=ADMIN_HEADERS,
    )
    assert offline_response.status_code == 200
    assert offline_response.json()["status"] == "offline"

    delete_response = client.delete(
        f"/api/v1/admin/templates/{second['id']}",
        headers=ADMIN_HEADERS,
    )
    assert delete_response.status_code == 204


def test_user_can_list_detail_clone_edit_use_and_generate_templates(client):
    category_id, tag_id = create_taxonomy(client)
    system_template = create_system_template(client, category_id, tag_id)
    publish_template(client, system_template["id"])

    user_template_response = client.post(
        "/api/v1/templates/user",
        headers=USER_HEADERS,
        json={
            "name": "我的模板",
            "description": "个人版本",
            "content": "我的正文",
            "category_id": category_id,
            "tag_ids": [tag_id],
        },
    )
    assert user_template_response.status_code == 200
    user_template = user_template_response.json()

    list_response = client.get("/api/v1/templates", headers={"x-user-id": "user-1"}, params={"scope": "all"})
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert {item["template_type"] for item in items} == {"system", "user"}
    assert {item["id"] for item in items} == {system_template["id"], user_template["id"]}

    detail_response = client.get(
        f"/api/v1/templates/{system_template['id']}",
        headers=USER_HEADERS,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "published"

    clone_response = client.post(
        f"/api/v1/templates/{system_template['id']}:clone",
        headers={"x-user-id": "user-1"},
    )
    assert clone_response.status_code == 200
    cloned = clone_response.json()
    assert cloned["template_type"] == "user"
    assert cloned["source_template_id"] == system_template["id"]

    patch_response = client.patch(
        f"/api/v1/templates/user/{cloned['id']}",
        headers={"x-user-id": "user-1"},
        json={"name": "复制后修改", "content": "新的正文"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "复制后修改"

    use_response = client.post(
        f"/api/v1/templates/{cloned['id']}:use",
        headers=USER_HEADERS,
    )
    assert use_response.status_code == 200
    assert use_response.json()["content"] == "新的正文"

    draft_response = client.post(
        "/api/v1/templates/drafts:generate",
        headers={"x-user-id": "user-1"},
        json={"prompt": "生成活动复盘模板", "context": "用于季度会议"},
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["generation_notes"] == "single_round_draft"
    before_count = len(store.templates)
    save_draft_response = client.post(
        "/api/v1/templates/user",
        headers=USER_HEADERS,
        json={
            "name": draft["name"],
            "description": draft["description"],
            "content": draft["content"],
            "category_id": category_id,
            "tag_ids": [tag_id],
            "ai_generated": True,
        },
    )
    assert save_draft_response.status_code == 200
    assert len(store.templates) == before_count + 1


def test_permissions_visibility_and_error_contract(client):
    category_id, tag_id = create_taxonomy(client)
    published = create_system_template(client, category_id, tag_id, content="可见正文")
    publish_template(client, published["id"])
    draft = create_system_template(client, category_id, tag_id, content="草稿正文")
    client.post(
        f"/api/v1/admin/templates/{draft['id']}:offline",
        headers=ADMIN_HEADERS,
    )

    user_template = client.post(
        "/api/v1/templates/user",
        headers=USER_HEADERS,
        json={
            "name": "仅自己可见",
            "description": "个人模板",
            "content": "个人正文",
            "category_id": category_id,
            "tag_ids": [tag_id],
        },
    ).json()

    unauth_list = client.get("/api/v1/templates")
    assert unauth_list.status_code == 401
    assert unauth_list.json()["error"]["code"] == "unauthorized"

    visible_response = client.get("/api/v1/templates", headers={"x-user-id": "user-1"})
    ids = {item["id"] for item in visible_response.json()["items"]}
    assert published["id"] in ids
    assert draft["id"] not in ids

    forbidden_admin = client.get("/api/v1/admin/templates", headers={"x-user-role": "user"})
    assert forbidden_admin.status_code == 403

    forbidden_user_detail = client.get(
        f"/api/v1/templates/{user_template['id']}",
        headers=OTHER_USER_HEADERS,
    )
    assert forbidden_user_detail.status_code == 403
    assert forbidden_user_detail.json()["error"]["code"] == "forbidden"

    forbidden_user_patch = client.patch(
        f"/api/v1/templates/user/{user_template['id']}",
        headers={"x-user-id": "user-2"},
        json={"content": "越权修改"},
    )
    assert forbidden_user_patch.status_code == 403

    bad_publish = client.post(
        "/api/v1/admin/templates",
        headers=ADMIN_HEADERS,
        json={
            "name": "缺正文模板",
            "description": "待发布",
            "content": "",
            "category_id": category_id,
            "tag_ids": [tag_id],
            "status": "draft",
        },
    ).json()
    publish_response = client.post(
        f"/api/v1/admin/templates/{bad_publish['id']}:publish",
        headers=ADMIN_HEADERS,
    )
    assert publish_response.status_code == 400
    body = publish_response.json()
    assert body["error"]["code"] == "validation_error"
    assert "request_id" in body

    delete_response = client.delete(
        f"/api/v1/templates/user/{user_template['id']}",
        headers={"x-user-id": "user-1"},
    )
    assert delete_response.status_code == 204
