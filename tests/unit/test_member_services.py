from __future__ import annotations

import pytest

from apps.backend.application.member_services import (
    growth_to_next_level,
    resolve_level,
    update_benefit_config,
    update_level_config,
)
from apps.backend.application.services import DomainError
from apps.backend.infrastructure.store import store


def test_resolve_level_and_next_growth_gap() -> None:
    store.reset()
    levels = store.member_published_config.levels
    current = resolve_level(35, levels)
    next_level, gap = growth_to_next_level(10, levels)

    assert current.code == "level_2"
    assert next_level == "level_2"
    assert gap == 20


def test_update_levels_rejects_unsorted_thresholds() -> None:
    store.reset()

    with pytest.raises(DomainError) as exc_info:
        update_level_config(
            "ops-1",
            "admin",
            [
                {"code": "level_2", "name": "成长会员", "growth_threshold": 30},
                {"code": "level_1", "name": "普通用户", "growth_threshold": 0},
            ],
        )

    assert exc_info.value.code == "invalid_level_order"


def test_update_benefits_rejects_unknown_level_reference() -> None:
    store.reset()

    with pytest.raises(DomainError) as exc_info:
        update_benefit_config(
            "ops-1",
            "admin",
            [
                {
                    "benefit_code": "vip_badge",
                    "level_code": "missing",
                    "name": "VIP Badge",
                    "is_enabled": True,
                }
            ],
        )

    assert exc_info.value.code == "invalid_benefit_level"
