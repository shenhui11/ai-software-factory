from __future__ import annotations

from copy import deepcopy

from apps.backend.domain.member_models import (
    BenefitConfig,
    BenefitMapping,
    LevelConfig,
    MemberConfigSnapshot,
    MemberEvent,
    MemberProfile,
    MemberTaskConfig,
    PointsAccount,
    PointsLedgerEntry,
    RewardRecord,
    UserTaskState,
)


def default_member_config() -> MemberConfigSnapshot:
    return MemberConfigSnapshot(
        version=1,
        published_at=None,
        tasks=[
            MemberTaskConfig(
                task_code="daily_check_in",
                title="Daily Check-in",
                task_type="daily_check_in",
                reward_points=10,
                daily_limit=1,
            ),
            MemberTaskConfig(
                task_code="complete_profile",
                title="Complete Profile",
                task_type="action",
                reward_points=20,
                daily_limit=1,
            ),
        ],
        levels=[
            LevelConfig(
                level=1,
                name="Regular",
                growth_threshold=0,
                description="Default member level",
            ),
            LevelConfig(
                level=2,
                name="Growth Member",
                growth_threshold=30,
                description="Unlocked after basic activity",
            ),
        ],
        benefits=[
            BenefitConfig(
                benefit_code="priority_badge",
                name="Priority Badge",
                description="Display a growth member badge",
                enabled=True,
            ),
        ],
        mappings=[BenefitMapping(level=2, benefit_code="priority_badge")],
    )


class MemberStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.member_profiles: dict[str, MemberProfile] = {}
        self.points_accounts: dict[str, PointsAccount] = {}
        self.ledger_entries: list[PointsLedgerEntry] = []
        self.reward_records: list[RewardRecord] = []
        self.member_events: list[MemberEvent] = []
        self.user_tasks: dict[tuple[str, str], UserTaskState] = {}
        self.staged_config = default_member_config()
        self.published_config = deepcopy(self.staged_config)
        self.next_config_version = self.staged_config.version + 1


member_store = MemberStore()
