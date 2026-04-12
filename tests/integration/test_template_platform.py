from __future__ import annotations

from apps.backend.infrastructure.store import store


def create_taxonomy(client, admin_headers):
    category = client.post(
        "/api/v1/admin/template-categories",
        headers=admin_headers,
        json={
            "name": "Campaign",
            "description": "Campaign templates",
            "sort_order": 1,
        },
    )
    assert category.status_code == 200
    tag = client.post(
        "/api/v1/admin/template-tags",
        headers=admin_headers,
        json={"name": "Launch", "description": "Launch assets"},
    )
    assert tag.status_code == 200
    return category.json(), tag.json()


def create_system_template(client, admin_headers, category_id: str, tag_id: str):
    response = client.post(
        "/api/v1/admin/templates",
        headers=admin_headers,
        json={
            "name": "Product Launch",
            "description": "Official launch template",
            "content": "Goal\nAudience\nMessage",
            "category_id": category_id,
            "tag_ids": [tag_id],
            "status": "draft",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_admin_can_manage_and_publish_system_template(client, admin_headers, user_headers):
    category, tag = create_taxonomy(client, admin_headers)
    template = create_system_template(client, admin_headers, category["id"], tag["id"])

    publish_response = client.post(
        f"/api/v1/admin/templates/{template['id']}:publish",
        headers=admin_headers,
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "published"

    admin_list = client.get(
        "/api/v1/admin/templates",
        headers=admin_headers,
        params={"status": "published", "keyword": "Launch"},
    )
    assert admin_list.status_code == 200
    assert len(admin_list.json()["items"]) == 1

    user_list = client.get(
        "/api/v1/templates",
        headers=user_headers,
        params={"scope": "all"},
    )
    assert user_list.status_code == 200
    assert user_list.json()["items"][0]["template_type"] == "system"

    detail = client.get(f"/api/v1/templates/{template['id']}", headers=user_headers)
    assert detail.status_code == 200
    assert detail.json()["tags"][0]["id"] == tag["id"]

    offline_response = client.post(
        f"/api/v1/admin/templates/{template['id']}:offline",
        headers=admin_headers,
    )
    assert offline_response.status_code == 200
    assert offline_response.json()["status"] == "offline"
    assert len(store.template_audit_events) >= 3


def test_user_template_clone_edit_use_and_snapshot_are_isolated(
    client,
    admin_headers,
    user_headers,
):
    category, tag = create_taxonomy(client, admin_headers)
    template = create_system_template(client, admin_headers, category["id"], tag["id"])
    client.post(f"/api/v1/admin/templates/{template['id']}:publish", headers=admin_headers)

    clone_response = client.post(
        f"/api/v1/templates/{template['id']}:clone",
        headers=user_headers,
    )
    assert clone_response.status_code == 200
    cloned = clone_response.json()
    assert cloned["template_type"] == "user"
    assert cloned["source_template_id"] == template["id"]

    edit_response = client.patch(
        f"/api/v1/templates/user/{cloned['id']}",
        headers=user_headers,
        json={"name": "My Launch", "content": "My private launch flow"},
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["name"] == "My Launch"

    use_response = client.post(
        f"/api/v1/templates/{cloned['id']}:use",
        headers=user_headers,
    )
    assert use_response.status_code == 200
    assert use_response.json()["content"] == "My private launch flow"

    client.patch(
        f"/api/v1/admin/templates/{template['id']}",
        headers=admin_headers,
        json={"content": "Official content updated"},
    )
    cloned_detail = client.get(f"/api/v1/templates/{cloned['id']}", headers=user_headers)
    assert cloned_detail.status_code == 200
    assert cloned_detail.json()["content"] == "My private launch flow"


def test_ai_draft_generation_requires_explicit_save(
    client,
    admin_headers,
    user_headers,
):
    category, tag = create_taxonomy(client, admin_headers)

    generate_response = client.post(
        "/api/v1/templates/drafts:generate",
        headers=user_headers,
        json={"prompt": "生成一个新品上线模板", "context": "面向社媒运营"},
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()
    assert generated["name"]
    assert store.template_generation_records
    assert store.templates == {}

    save_response = client.post(
        "/api/v1/templates/user",
        headers=user_headers,
        json={
            "name": generated["name"],
            "description": generated["description"],
            "content": generated["content"],
            "category_id": category["id"],
            "tag_ids": [tag["id"]],
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["owner_user_id"] == "user-1"


def test_permissions_and_visibility_are_enforced(
    client,
    admin_headers,
    user_headers,
    other_user_headers,
):
    category, tag = create_taxonomy(client, admin_headers)
    template = create_system_template(client, admin_headers, category["id"], tag["id"])
    client.post(f"/api/v1/admin/templates/{template['id']}:publish", headers=admin_headers)

    unauthenticated = client.get("/api/v1/templates")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "authentication_required"

    forbidden_admin = client.get("/api/v1/admin/templates", headers=user_headers)
    assert forbidden_admin.status_code == 403

    user_template = client.post(
        "/api/v1/templates/user",
        headers=user_headers,
        json={
            "name": "Private Notes",
            "description": "Only mine",
            "content": "Private content",
            "category_id": category["id"],
            "tag_ids": [tag["id"]],
        },
    ).json()
    hidden_detail = client.get(
        f"/api/v1/templates/{user_template['id']}",
        headers=other_user_headers,
    )
    assert hidden_detail.status_code == 404


def test_unpublished_or_offline_system_templates_are_hidden_from_users(
    client,
    admin_headers,
    user_headers,
):
    category, tag = create_taxonomy(client, admin_headers)
    draft = create_system_template(client, admin_headers, category["id"], tag["id"])
    published = create_system_template(client, admin_headers, category["id"], tag["id"])
    offline = create_system_template(client, admin_headers, category["id"], tag["id"])
    client.post(f"/api/v1/admin/templates/{published['id']}:publish", headers=admin_headers)
    client.post(f"/api/v1/admin/templates/{offline['id']}:publish", headers=admin_headers)
    client.post(f"/api/v1/admin/templates/{offline['id']}:offline", headers=admin_headers)

    response = client.get("/api/v1/templates", headers=user_headers)
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert published["id"] in ids
    assert draft["id"] not in ids
    assert offline["id"] not in ids
