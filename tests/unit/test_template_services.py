from __future__ import annotations

import pytest

from apps.backend.application.services import DomainError
from apps.backend.infrastructure.store import store
from apps.backend.template.models import Actor, Template, TemplateCategory, TemplateTag
from apps.backend.template import services


@pytest.fixture()
def actor() -> Actor:
    store.reset()
    category = TemplateCategory(name="Ops", description="Ops")
    tag = TemplateTag(name="Starter", description="Starter")
    store.template_categories[category.id] = category
    store.template_tags[tag.id] = tag
    return Actor(user_id="user-1", role="user")


def test_duplicate_tag_ids_are_rejected(actor: Actor):
    category_id = next(iter(store.template_categories))
    tag_id = next(iter(store.template_tags))
    with pytest.raises(DomainError) as exc_info:
        services.create_user_template(
            actor,
            {
                "name": "Template",
                "description": "",
                "content": "Content",
                "category_id": category_id,
                "tag_ids": [tag_id, tag_id],
            },
        )
    assert exc_info.value.code == "duplicate_tag"


def test_clone_preserves_snapshot_after_source_changes(actor: Actor):
    category_id = next(iter(store.template_categories))
    tag_id = next(iter(store.template_tags))
    source = Template(
        template_type="system",
        status="published",
        name="Source",
        description="Desc",
        content="Initial content",
        category_id=category_id,
        creator_user_id="admin-1",
        owner_user_id=None,
        tag_ids=[tag_id],
    )
    store.templates[source.id] = source

    cloned = services.clone_system_template(actor, source.id)
    source.content = "Changed after clone"
    detail = services.get_template_detail(actor, cloned["id"])

    assert detail["content"] == "Initial content"
    assert detail["source_template_id"] == source.id


def test_non_owner_cannot_access_user_template(actor: Actor):
    category_id = next(iter(store.template_categories))
    user_template = Template(
        template_type="user",
        status="draft",
        name="Private",
        description="",
        content="Secret",
        category_id=category_id,
        creator_user_id="user-1",
        owner_user_id="user-1",
    )
    store.templates[user_template.id] = user_template

    with pytest.raises(DomainError) as exc_info:
        services.get_template_detail(Actor(user_id="user-2", role="user"), user_template.id)
    assert exc_info.value.code == "template_not_found"
