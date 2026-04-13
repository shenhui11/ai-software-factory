from __future__ import annotations

from apps.backend.application.member_services import (
    _growth_to_next_level,
    _membership_status_for_level,
    _resolve_level,
    _validate_benefits,
    _validate_levels,
)
from apps.backend.application.services import DomainError
from apps.backend.domain.member_models import (
    BenefitConfig,
    BenefitMapping,
    LevelConfig,
    MemberConfigSnapshot,
)


def test_membership_status_changes_after_level_one() -> None:
    assert _membership_status_for_level(1) == "regular"
    assert _membership_status_for_level(2) == "growth_member"


def test_growth_to_next_level_is_zero_when_already_maxed() -> None:
    assert _growth_to_next_level(50, None) == 0


def test_resolve_level_uses_highest_eligible_threshold() -> None:
    levels = [
        LevelConfig(level=1, name="L1", growth_threshold=0, description=""),
        LevelConfig(level=2, name="L2", growth_threshold=30, description=""),
        LevelConfig(level=3, name="L3", growth_threshold=60, description=""),
    ]
    resolved = _resolve_level(levels, 45)
    assert resolved.level == 2


def test_validate_levels_rejects_duplicate_codes() -> None:
    levels = [
        LevelConfig(level=1, name="L1", growth_threshold=0, description=""),
        LevelConfig(level=1, name="L1b", growth_threshold=10, description=""),
    ]
    try:
        _validate_levels(levels)
    except DomainError as exc:
        assert exc.code == "duplicate_level_code"
    else:
        raise AssertionError("Expected duplicate level validation error")


def test_validate_benefits_rejects_unknown_level() -> None:
    snapshot = MemberConfigSnapshot(
        version=1,
        published_at=None,
        tasks=[],
        levels=[LevelConfig(level=1, name="L1", growth_threshold=0, description="")],
        benefits=[BenefitConfig(benefit_code="badge", name="Badge", description="")],
        mappings=[BenefitMapping(level=2, benefit_code="badge")],
    )
    try:
        _validate_benefits(snapshot)
    except DomainError as exc:
        assert exc.code == "invalid_benefit_level"
    else:
        raise AssertionError("Expected invalid benefit level validation error")
