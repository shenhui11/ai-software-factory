from __future__ import annotations

from copy import deepcopy

from apps.backend.domain.models import (
    AuditEvent,
    BenefitDefinition,
    BenefitMapping,
    DraftConfig,
    LedgerEntry,
    LevelRule,
    MemberProfile,
    PointsAccount,
    PublishedConfig,
    RewardRecord,
    TaskDefinition,
    TaskRecord,
    utc_now,
)


def build_default_config() -> PublishedConfig:
    tasks = {
        "daily_check_in": TaskDefinition(
            task_code="daily_check_in",
            title="Daily Check-in",
            task_type="check_in",
            reward_points=10,
            daily_limit=1,
        ),
        "complete_profile": TaskDefinition(
            task_code="complete_profile",
            title="Complete Profile",
            task_type="manual",
            reward_points=30,
            daily_limit=1,
        ),
    }
    levels = [
        LevelRule("L1", "Regular", 0, "Default membership level"),
        LevelRule("L2", "Growth Member", 40, "Unlocked after earning 40 growth"),
    ]
    benefits = {
        "member_badge": BenefitDefinition(
            benefit_code="member_badge",
            title="Growth Member Badge",
            description="Display the growth member badge in the dashboard.",
        )
    }
    mappings = {
        "L2": BenefitMapping(level_code="L2", benefit_codes=["member_badge"])
    }
    return PublishedConfig(
        version=1,
        published_at=utc_now(),
        tasks=tasks,
        levels=levels,
        benefits=benefits,
        benefit_mappings=mappings,
    )


class InMemoryStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.member_profiles: dict[str, MemberProfile] = {}
        self.points_accounts: dict[str, PointsAccount] = {}
        self.task_records: dict[tuple[str, str, str], TaskRecord] = {}
        self.ledger_entries: list[LedgerEntry] = []
        self.reward_records: list[RewardRecord] = []
        self.audit_events: list[AuditEvent] = []
        self.request_action_index: dict[tuple[str, str, str], str] = {}
        self.risk_windows: dict[tuple[str, str], list] = {}
        default_config = build_default_config()
        self.published_config = default_config
        self.draft_config = DraftConfig(
            tasks=deepcopy(default_config.tasks),
            levels=deepcopy(default_config.levels),
            benefits=deepcopy(default_config.benefits),
            benefit_mappings=deepcopy(default_config.benefit_mappings),
        )


store = InMemoryStore()
