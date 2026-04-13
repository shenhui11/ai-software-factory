from __future__ import annotations

from apps.backend.application.services import DomainError
from apps.backend.application import template_services
from apps.backend.infrastructure.store import store


def seed_taxonomy() -> tuple[str, str]:
    category = template_services.create_category(
        name="Marketing",
        description="Marketing templates",
        sort_order=1,
        is_active=True,
        user_role="admin",
    )
    tag = template_services.create_tag(
        name="Launch",
        description="Launch tag",
        is_active=True,
        user_role="admin",
    )
    return category.id, tag.id


def test_publish_requires_required_fields() -> None:
    store.reset()
    category_id, tag_id = seed_taxonomy()
    template = template_services.create_system_template(
        payload={
            "name": "Incomplete",
            "description": "Missing content",
            "content": "",
            "category_id": category_id,
            "tag_ids": [tag_id],
            "status": "draft",
        },
        user_id="admin-1",
        user_role="admin",
    )
    try:
        template_services.publish_system_template(
            template_id=template["id"],
            user_id="admin-1",
            user_role="admin",
        )
    except DomainError as exc:
        assert exc.code == "validation_error"
        assert store.templates[template["id"]].status == "draft"
    else:
        raise AssertionError("publish should have failed")


def test_clone_preserves_snapshot_after_source_changes() -> None:
    store.reset()
    category_id, tag_id = seed_taxonomy()
    source = template_services.create_system_template(
        payload={
            "name": "Source",
            "description": "Original",
            "content": "Version 1",
            "category_id": category_id,
            "tag_ids": [tag_id],
            "status": "draft",
        },
        user_id="admin-1",
        user_role="admin",
    )
    template_services.publish_system_template(
        template_id=source["id"],
        user_id="admin-1",
        user_role="admin",
    )
    cloned = template_services.clone_system_template(
        template_id=source["id"],
        user_id="user-1",
    )
    template_services.update_system_template(
        template_id=source["id"],
        payload={"content": "Version 2"},
        user_id="admin-1",
        user_role="admin",
    )
    assert store.templates[cloned["id"]].content == "Version 1"
    assert store.templates[cloned["id"]].source_template_id == source["id"]


def test_non_owner_cannot_update_user_template() -> None:
    store.reset()
    category_id, tag_id = seed_taxonomy()
    template = template_services.create_user_template(
        payload={
            "name": "Private",
            "description": "Mine",
            "content": "Secret",
            "category_id": category_id,
            "tag_ids": [tag_id],
        },
        user_id="owner-1",
    )
    try:
        template_services.update_user_template(
            template_id=template["id"],
            payload={"content": "Hacked"},
            user_id="owner-2",
        )
    except DomainError as exc:
        assert exc.code == "forbidden"
    else:
        raise AssertionError("update should have failed")
