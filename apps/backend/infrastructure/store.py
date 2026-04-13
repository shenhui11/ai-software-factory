from __future__ import annotations

from dataclasses import asdict
from typing import Any

from apps.backend.domain.models import (
    BenefitConfig,
    Chapter,
    ChapterVersion,
    LevelConfig,
    MemberAuditEvent,
    MemberConfigSnapshot,
    MemberProfile,
    MemberTaskConfig,
    MemberTaskRecord,
    ParagraphEditSuggestion,
    PointsAccount,
    PointsLedgerEntry,
    QaIssue,
    QaScan,
    RewardRecord,
    StoryCanon,
    StoryOutline,
    StoryProject,
)
from apps.backend.domain.template_models import (
    Template,
    TemplateAuditEvent,
    TemplateCategory,
    TemplateGenerationRecord,
    TemplateTag,
)


class InMemoryStore:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.projects: dict[str, StoryProject] = {}
        self.canons: dict[str, StoryCanon] = {}
        self.outlines: dict[str, StoryOutline] = {}
        self.chapters: dict[str, Chapter] = {}
        self.versions: dict[str, ChapterVersion] = {}
        self.chapter_versions: dict[str, list[str]] = {}
        self.edit_suggestions: dict[str, ParagraphEditSuggestion] = {}
        self.scans: dict[str, QaScan] = {}
        self.chapter_scans: dict[str, list[str]] = {}
        self.issues: dict[str, QaIssue] = {}
        self.templates: dict[str, Template] = {}
        self.template_categories: dict[str, TemplateCategory] = {}
        self.template_tags: dict[str, TemplateTag] = {}
        self.template_generation_records: dict[str, TemplateGenerationRecord] = {}
        self.template_audit_events: dict[str, TemplateAuditEvent] = {}
        self.member_profiles: dict[str, MemberProfile] = {}
        self.points_accounts: dict[str, PointsAccount] = {}
        self.member_task_records: dict[str, MemberTaskRecord] = {}
        self.points_ledger_entries: dict[str, PointsLedgerEntry] = {}
        self.reward_records: dict[str, RewardRecord] = {}
        self.member_audit_events: dict[str, MemberAuditEvent] = {}
        self.member_published_config = self._default_member_config(version=1)
        self.member_working_config = self._default_member_config(version=1)

    def dump_project_state(self, project_id: str) -> dict[str, Any]:
        project = self.projects[project_id]
        canon = self.canons.get(project_id)
        outline = self.outlines.get(project_id)
        return {
            "project": asdict(project),
            "canon": asdict(canon) if canon else None,
            "outline": asdict(outline) if outline else None,
        }

    def _default_member_config(self, version: int) -> MemberConfigSnapshot:
        return MemberConfigSnapshot(
            version=version,
            tasks=[
                MemberTaskConfig(
                    task_code="daily_check_in",
                    task_type="check_in",
                    title="每日签到",
                    description="每日签到获取成长积分",
                    is_enabled=True,
                    reward_points=10,
                    daily_limit=1,
                    window_rule="daily",
                    trigger_source="member_panel",
                    config_version=version,
                ),
                MemberTaskConfig(
                    task_code="complete_profile",
                    task_type="manual_action",
                    title="完善资料",
                    description="完成资料填写获取成长积分",
                    is_enabled=True,
                    reward_points=25,
                    daily_limit=1,
                    window_rule="daily",
                    trigger_source="manual",
                    config_version=version,
                ),
            ],
            levels=[
                LevelConfig(
                    code="level_1",
                    name="普通用户",
                    growth_threshold=0,
                    description="默认等级",
                ),
                LevelConfig(
                    code="level_2",
                    name="成长会员",
                    growth_threshold=30,
                    description="解锁成长权益",
                ),
            ],
            benefits=[
                BenefitConfig(
                    benefit_code="growth_badge",
                    level_code="level_2",
                    name="成长会员标识",
                    description="会员面板展示成长会员标识",
                    is_enabled=True,
                    metadata={"badge": "growth_member"},
                )
            ],
        )


store = InMemoryStore()
