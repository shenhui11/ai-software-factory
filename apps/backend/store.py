from __future__ import annotations

from apps.backend.models import (
    AuditLog,
    MembershipPlan,
    Order,
    Project,
    SafetyPolicy,
    Template,
    UserQuota,
    new_id,
)


class InMemoryStore:
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.templates: dict[str, Template] = {
            "tpl-system-romance": Template(
                id="tpl-system-romance",
                name="Romance Starter",
                genre="romance",
                style_rules="Warm emotional pacing",
                world_template="Modern city backdrop",
                character_template="Lead pair with conflicting goals",
                outline_template="Meet, clash, reveal, reconcile",
                status="published",
            ),
            "tpl-user-fantasy": Template(
                id="tpl-user-fantasy",
                name="Fantasy Quest",
                genre="fantasy",
                style_rules="High stakes and vivid worldbuilding",
                world_template="Fragmented kingdom and ancient relics",
                character_template="Hero, rival, mentor",
                outline_template="Call, test, setback, breakthrough",
                status="draft",
                owner_type="user",
            ),
        }
        self.membership_plans: dict[str, MembershipPlan] = {
            "plan-basic": MembershipPlan(
                id="plan-basic",
                name="Basic",
                free_chapter_quota=5,
                monthly_quota=20,
            )
        }
        self.user_quota = UserQuota(free_remaining=5, monthly_remaining=20)
        self.orders: dict[str, Order] = {
            "order-001": Order(
                id="order-001",
                plan_id="plan-basic",
                amount=9.9,
                status="paid",
            )
        }
        self.safety_policy = SafetyPolicy(
            id="policy-default",
            blocked_terms=["forbidden", "banned"],
            copyright_notice="Generated content should be reviewed before publication.",
        )
        self.audit_logs: list[AuditLog] = []

    def log(self, action: str, details: dict[str, object]) -> None:
        self.audit_logs.append(AuditLog(id=new_id("log"), action=action, details=details))


store = InMemoryStore()
