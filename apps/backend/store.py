from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from apps.backend.models import (
    AuditLog,
    Chapter,
    ChapterDraft,
    ChapterTask,
    FoundationTaskStatus,
    GenreConfig,
    MembershipPlan,
    Order,
    OutlineOption,
    Project,
    ProjectFoundationTask,
    ProjectMemory,
    SafetyPolicy,
    TaskMode,
    TaskStatus,
    Template,
    UserQuota,
    new_id,
)

try:  # pragma: no cover - optional dependency
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - keep local tests working without postgres driver
    psycopg = None
    dict_row = None


DEFAULT_APP_DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"
APP_BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _default_templates() -> dict[str, Template]:
    return {
        "tpl-system-romance": Template(
            id="tpl-system-romance",
            name="言情开篇模板",
            genre="romance",
            genres=["romance"],
            tags=["情感", "都市", "开篇"],
            style_rules="情绪推进细腻，节奏温暖克制",
            world_template="现代都市背景",
            character_template="目标冲突明显的男女主",
            outline_template="相遇、碰撞、揭露、和解",
            status="published",
            usage_count=3,
        ),
        "tpl-user-fantasy": Template(
            id="tpl-user-fantasy",
            name="玄幻冒险模板",
            genre="fantasy",
            genres=["fantasy"],
            tags=["冒险", "成长", "王国"],
            style_rules="高风险推进，强化世界细节",
            world_template="破碎王国与远古遗物",
            character_template="主角、宿敌、导师",
            outline_template="召唤、试炼、受挫、突破",
            status="draft",
            owner_type="user",
            usage_count=1,
        ),
    }


def _default_genre_configs() -> dict[str, GenreConfig]:
    return {
        "romance": GenreConfig(value="romance", label="言情", required_any=["目光", "停顿", "心口", "呼吸", "误会"], forbidden_any=["法医", "验尸", "主控室", "数据库", "控制台", "实验员"]),
        "fantasy": GenreConfig(value="fantasy", label="玄幻", required_any=["灵气", "法则", "异象", "秘境", "血脉", "古殿", "因果"], forbidden_any=["实验室", "病历", "控制台", "数据库", "主控室", "实验员", "回收舱", "监控死角", "物流中心", "电子音", "平板"]),
        "horror": GenreConfig(value="horror", label="恐怖", required_any=["异响", "阴影", "寒意", "血迹", "脚步声", "腐臭"], forbidden_any=["轻松插科打诨", "无代价开挂", "温馨日常", "热血口号"]),
        "wuxia": GenreConfig(value="wuxia", label="武侠", required_any=["江湖", "内力", "门派", "招式", "侠义"], forbidden_any=["实验室", "病历", "控制台", "数据库", "实验员", "电子音", "平板", "回收舱"]),
        "xianxia": GenreConfig(value="xianxia", label="仙侠", required_any=["灵气", "真元", "金丹", "元婴", "宗门", "法宝", "因果"], forbidden_any=["实验室", "病历", "控制台", "数据库", "主控室", "实验员", "回收舱", "监控", "平板"]),
        "sci_fi": GenreConfig(value="sci_fi", label="科幻", required_any=["系统", "协议", "接口", "参数", "信号", "算法"], forbidden_any=[]),
        "suspense": GenreConfig(value="suspense", label="悬疑", required_any=["线索", "疑点", "证据", "误导", "推断"], forbidden_any=[]),
        "historical": GenreConfig(value="historical", label="历史", required_any=["朝堂", "礼制", "门第", "诏令", "边关", "年号"], forbidden_any=["现代口水话", "控制台", "数据库", "实验员"]),
        "urban": GenreConfig(value="urban", label="都市", required_any=["地铁", "写字楼", "街区", "租房", "咖啡店", "手机"], forbidden_any=["全篇古风措辞", "宗门境界", "朝堂礼制"]),
        "mystery": GenreConfig(value="mystery", label="推理", required_any=["线索", "推断", "不在场证明", "疑点", "反证", "真相"], forbidden_any=["无依据顿悟", "纯靠外挂预知", "只讲设定不推理"]),
        "thriller": GenreConfig(value="thriller", label="惊悚", required_any=["追逼", "失控", "倒计时", "危险", "逃生", "压迫感"], forbidden_any=["长篇静态设定讲解", "温吞日常", "无风险闲聊"]),
        "detective": GenreConfig(value="detective", label="侦探", required_any=["案发", "走访", "证词", "嫌疑人", "痕迹", "侦查"], forbidden_any=["无证据定案", "纯玄学破案", "主线改成热血升级"]),
        "military": GenreConfig(value="military", label="军事", required_any=["部队", "命令", "阵地", "火力", "侦察", "战术"], forbidden_any=["儿女情长主导全章", "控制台解谜", "宫斗腔"]),
        "game": GenreConfig(value="game", label="游戏", required_any=["副本", "任务", "面板", "装备", "技能", "通关"], forbidden_any=["纯现实职场流程", "朝堂礼制", "法医验尸"]),
        "esports": GenreConfig(value="esports", label="电竞", required_any=["战队", "训练赛", "操作", "BP", "赛点", "联赛"], forbidden_any=["修仙境界", "朝堂权谋", "实验室惊悚"]),
        "workplace": GenreConfig(value="workplace", label="职场", required_any=["项目", "汇报", "客户", "会议", "绩效", "晋升"], forbidden_any=["全篇打怪升级", "门派修行", "无现实约束恋爱脑"]),
        "campus": GenreConfig(value="campus", label="校园", required_any=["教室", "宿舍", "考试", "社团", "操场", "老师"], forbidden_any=["朝堂权谋", "军事战术主线", "职场会议腔"]),
        "youth": GenreConfig(value="youth", label="青春", required_any=["成长", "冲动", "同伴", "倔强", "告别", "选择"], forbidden_any=["官场黑话", "硬科幻说明书", "纯家长里短絮叨"]),
        "family": GenreConfig(value="family", label="家庭", required_any=["父母", "子女", "婚姻", "照料", "争执", "和解"], forbidden_any=["升级打怪主导", "实验室惊悚", "空泛鸡汤总结"]),
        "adventure": GenreConfig(value="adventure", label="冒险", required_any=["启程", "险地", "遗迹", "追踪", "同伴", "未知"], forbidden_any=["原地空谈", "长篇办公室流程", "全程无行动"]),
        "action": GenreConfig(value="action", label="动作", required_any=["追击", "闪避", "爆发", "近身", "反击", "突围"], forbidden_any=["冗长说明", "静态会议", "纯感情拉扯"]),
        "martial_arts": GenreConfig(value="martial_arts", label="热血", required_any=["燃起", "不服", "对决", "成长", "突破", "拼到底"], forbidden_any=["阴柔悬疑主导", "长篇政务流程", "无行动只说理"]),
        "post_apocalypse": GenreConfig(value="post_apocalypse", label="末世", required_any=["废墟", "物资", "感染", "避难所", "秩序崩坏", "求生"], forbidden_any=["温馨校园日常", "朝堂礼制", "纯恋爱喜剧"]),
        "cyberpunk": GenreConfig(value="cyberpunk", label="赛博朋克", required_any=["义体", "企业", "霓虹", "黑客", "接口", "数据黑市"], forbidden_any=["纯古风王朝", "田园日常", "传统武侠门派"]),
        "steampunk": GenreConfig(value="steampunk", label="蒸汽朋克", required_any=["蒸汽", "齿轮", "工坊", "机械臂", "飞艇", "煤烟"], forbidden_any=["纯现代电子产品", "宗门修仙", "校园恋爱日常"]),
        "space_opera": GenreConfig(value="space_opera", label="太空歌剧", required_any=["舰队", "星门", "殖民地", "航道", "帝国", "宇宙战"], forbidden_any=["小区家长里短", "门派修炼", "办公室汇报"]),
        "dystopian": GenreConfig(value="dystopian", label="反乌托邦", required_any=["统治", "规训", "监视", "等级", "服从", "反抗"], forbidden_any=["温馨治愈日常", "无压迫世界", "纯后宫轻喜"]),
        "time_travel": GenreConfig(value="time_travel", label="穿越", required_any=["异世", "前身", "时代差", "改命", "初来乍到", "身份落差"], forbidden_any=["完全不体现时代错位", "纯数据库调查", "现代白领流程原样照搬"]),
        "rebirth": GenreConfig(value="rebirth", label="重生", required_any=["前世", "再来一次", "弥补", "改写", "提前布局", "遗憾"], forbidden_any=["失去重生信息优势", "纯随机推进", "完全不提旧因果"]),
        "alternate_history": GenreConfig(value="alternate_history", label="架空历史", required_any=["王朝", "疆域", "制度", "世族", "兵变", "新政"], forbidden_any=["现代办公室黑话", "实验室主控台", "电竞术语主导"]),
        "palace_intrigue": GenreConfig(value="palace_intrigue", label="宫斗", required_any=["后宫", "恩宠", "位份", "试探", "借刀", "算计"], forbidden_any=["现代职场汇报", "实验室惊悚", "热血打怪升级"]),
        "court_politics": GenreConfig(value="court_politics", label="权谋", required_any=["朝局", "党争", "布局", "试探", "博弈", "制衡"], forbidden_any=["纯恋爱误会流", "实验室逃生", "校园日常"]),
        "cultivation": GenreConfig(value="cultivation", label="修真", required_any=["灵气", "境界", "突破", "丹药", "功法", "宗门", "识海"], forbidden_any=["实验室", "病历", "控制台", "数据库", "主控室", "实验员", "回收舱", "监控"]),
        "monster_taming": GenreConfig(value="monster_taming", label="御兽", required_any=["灵宠", "契约", "驯养", "进化", "兽栏", "血契"], forbidden_any=["实验室惊悚主导", "纯朝堂博弈", "无伙伴培养"]),
        "livestream": GenreConfig(value="livestream", label="直播", required_any=["直播间", "弹幕", "打赏", "连麦", "热度", "开播"], forbidden_any=["完全离线叙事", "朝堂礼制", "宗门修仙术语主导"]),
        "fanfiction": GenreConfig(value="fanfiction", label="同人", required_any=["原作角色", "既有设定", "世界观沿用", "改编关系", "二创"], forbidden_any=["完全脱离原作锚点", "无角色辨识度", "硬改成无关题材"]),
        "slice_of_life": GenreConfig(value="slice_of_life", label="日常", required_any=["做饭", "收拾", "通勤", "闲聊", "琐事", "生活感"], forbidden_any=["强行炸裂反转", "无来由生死大战", "说明书式设定堆砌"]),
    }


def _merge_genre_config(existing: GenreConfig, default: GenreConfig) -> GenreConfig:
    return GenreConfig(
        value=existing.value or default.value,
        label=existing.label or default.label,
        required_any=existing.required_any or default.required_any,
        forbidden_any=existing.forbidden_any or default.forbidden_any,
    )


def _default_membership_plans() -> dict[str, MembershipPlan]:
    return {
        "plan-basic": MembershipPlan(
            id="plan-basic",
            name="基础套餐",
            daily_free_chapters=5,
            monthly_free_chapters=50,
            description="适合单本小说试运行。",
        )
    }


def _default_orders() -> dict[str, Order]:
    return {
        "order-001": Order(
            id="order-001",
            plan_id="plan-basic",
            amount=9.9,
            status="已支付",
            note="初始化演示订单",
        )
    }


def _default_safety_policy() -> SafetyPolicy:
    return SafetyPolicy(
        id="policy-default",
        blocked_terms=["禁忌仪式", "封禁设定"],
        copyright_notice="AI 生成内容在发布前应由创作者完成人工复核。",
    )


class InMemoryStore:
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.foundation_tasks: dict[str, ProjectFoundationTask] = {}
        self.templates: dict[str, Template] = _default_templates()
        self.genre_configs: dict[str, GenreConfig] = _default_genre_configs()
        self.membership_plans: dict[str, MembershipPlan] = _default_membership_plans()
        self.active_plan_id = "plan-basic"
        self.user_quota = UserQuota(daily_remaining=5, monthly_remaining=50, bonus_remaining=0)
        self.user_active_plan_ids: dict[str, str] = {}
        self.user_quotas: dict[str, UserQuota] = {}
        self.orders: dict[str, Order] = _default_orders()
        self.safety_policy = _default_safety_policy()
        self.audit_logs: list[AuditLog] = []

    def save_project(self, project: Project) -> None:
        self.projects[project.id] = project

    def save_foundation_task(self, task: ProjectFoundationTask) -> None:
        self.foundation_tasks[task.id] = task

    def get_foundation_task(self, task_id: str) -> ProjectFoundationTask | None:
        return self.foundation_tasks.get(task_id)

    def delete_project(self, project_id: str) -> None:
        self.projects.pop(project_id, None)

    def save_template(self, template: Template) -> None:
        self.templates[template.id] = template

    def save_genre_config(self, config: GenreConfig) -> None:
        self.genre_configs[config.value] = config

    def save_membership_plan(self, plan: MembershipPlan) -> None:
        self.membership_plans[plan.id] = plan

    def save_order(self, order: Order) -> None:
        self.orders[order.id] = order

    def save_quota(self) -> None:
        return None

    def save_active_plan(self) -> None:
        return None

    def ensure_user_state(self, user_id: str) -> None:
        if user_id not in self.user_active_plan_ids:
            self.user_active_plan_ids[user_id] = self.active_plan_id
        if user_id not in self.user_quotas:
            plan = self.membership_plans[self.user_active_plan_ids[user_id]]
            self.user_quotas[user_id] = UserQuota(
                daily_remaining=plan.daily_free_chapters,
                monthly_remaining=plan.monthly_free_chapters,
                bonus_remaining=0,
            )

    def get_user_quota(self, user_id: str) -> UserQuota:
        self.ensure_user_state(user_id)
        return self.user_quotas[user_id]

    def get_user_active_plan_id(self, user_id: str) -> str:
        self.ensure_user_state(user_id)
        return self.user_active_plan_ids[user_id]

    def save_user_quota(self, user_id: str) -> None:
        self.ensure_user_state(user_id)

    def save_user_active_plan(self, user_id: str) -> None:
        self.ensure_user_state(user_id)

    def migrate_user_state_alias(self, canonical_user_id: str, legacy_user_key: str | None) -> None:
        legacy_key = (legacy_user_key or "").strip()
        if not legacy_key or legacy_key == canonical_user_id:
            return
        legacy_quota = self.user_quotas.get(legacy_key)
        legacy_plan_id = self.user_active_plan_ids.get(legacy_key)
        print(
            (
                f"[quota_alias] start canonical_user_id={canonical_user_id} legacy_user_key={legacy_key} "
                f"legacy_quota={legacy_quota.model_dump() if legacy_quota else None} "
                f"legacy_plan_id={legacy_plan_id} "
                f"canonical_quota={self.user_quotas.get(canonical_user_id).model_dump() if self.user_quotas.get(canonical_user_id) else None} "
                f"canonical_plan_id={self.user_active_plan_ids.get(canonical_user_id)}"
            ),
            flush=True,
        )
        if legacy_quota is None and legacy_plan_id is None:
            return
        self.ensure_user_state(canonical_user_id)
        canonical_quota = self.user_quotas[canonical_user_id]
        if legacy_quota is not None:
            canonical_quota.bonus_remaining = max(canonical_quota.bonus_remaining, legacy_quota.bonus_remaining)
            canonical_quota.monthly_remaining = max(canonical_quota.monthly_remaining, legacy_quota.monthly_remaining)
            canonical_quota.daily_remaining = max(canonical_quota.daily_remaining, legacy_quota.daily_remaining)
        if legacy_plan_id and self.user_active_plan_ids.get(canonical_user_id) == self.active_plan_id:
            self.user_active_plan_ids[canonical_user_id] = legacy_plan_id
        self.user_quotas.pop(legacy_key, None)
        self.user_active_plan_ids.pop(legacy_key, None)
        print(
            (
                f"[quota_alias] merged canonical_user_id={canonical_user_id} legacy_user_key={legacy_key} "
                f"canonical_quota={self.user_quotas[canonical_user_id].model_dump()} "
                f"canonical_plan_id={self.user_active_plan_ids.get(canonical_user_id)}"
            ),
            flush=True,
        )

    def save_safety_policy(self) -> None:
        return None

    def log(self, action: str, details: dict[str, object]) -> None:
        self.audit_logs.append(AuditLog(id=new_id("log"), action=action, details=details))

    def get_default_plan(self) -> MembershipPlan:
        return self.membership_plans[self.active_plan_id]

    def refresh_quota_periods(self, user_id: str | None = None) -> UserQuota:
        quota = self.get_user_quota(user_id or "") if user_id is not None else self.user_quota
        plan_id = self.get_user_active_plan_id(user_id or "") if user_id is not None else self.active_plan_id
        plan = self.membership_plans[plan_id]
        now = datetime.now(timezone.utc)
        last_daily_local = quota.last_daily_reset_at.astimezone(APP_BUSINESS_TIMEZONE).date()
        now_local = now.astimezone(APP_BUSINESS_TIMEZONE)
        if last_daily_local != now_local.date():
            quota.daily_remaining = plan.daily_free_chapters
            quota.last_daily_reset_at = now
        last_monthly_local = quota.last_monthly_reset_at.astimezone(APP_BUSINESS_TIMEZONE)
        if (
            last_monthly_local.year != now_local.year
            or last_monthly_local.month != now_local.month
        ):
            quota.monthly_remaining = plan.monthly_free_chapters
            quota.last_monthly_reset_at = now
        if user_id is not None:
            self.save_user_quota(user_id)
        else:
            self.save_quota()
        return quota


class SqliteStore(InMemoryStore):
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or os.getenv("APP_DB_PATH", str(DEFAULT_APP_DB_PATH)))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__()
        self._init_schema()
        self._load_all()
        self._ensure_seed_data()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS foundation_tasks (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS templates (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS genre_configs (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS membership_plans (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    id TEXT PRIMARY KEY,
                    active_plan_id TEXT NOT NULL,
                    free_remaining INTEGER NOT NULL,
                    monthly_remaining INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS safety_policy (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(app_state)").fetchall()}
            if "daily_remaining" not in columns:
                connection.execute("ALTER TABLE app_state ADD COLUMN daily_remaining INTEGER NOT NULL DEFAULT 0")
            if "bonus_remaining" not in columns:
                connection.execute("ALTER TABLE app_state ADD COLUMN bonus_remaining INTEGER NOT NULL DEFAULT 0")
            if "last_daily_reset_at" not in columns:
                connection.execute("ALTER TABLE app_state ADD COLUMN last_daily_reset_at TEXT NOT NULL DEFAULT ''")
            if "last_monthly_reset_at" not in columns:
                connection.execute("ALTER TABLE app_state ADD COLUMN last_monthly_reset_at TEXT NOT NULL DEFAULT ''")
            connection.execute(
                """
                UPDATE app_state
                SET bonus_remaining = CASE WHEN bonus_remaining = 0 THEN free_remaining ELSE bonus_remaining END
                """
            )
            connection.commit()

    def reset_for_tests(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                DELETE FROM projects;
                DELETE FROM foundation_tasks;
                DELETE FROM templates;
                DELETE FROM genre_configs;
                DELETE FROM membership_plans;
                DELETE FROM orders;
                DELETE FROM app_state;
                DELETE FROM safety_policy;
                DELETE FROM audit_logs;
                """
            )
            connection.commit()
        self.projects = {}
        self.foundation_tasks = {}
        self.templates = {}
        self.genre_configs = {}
        self.membership_plans = {}
        self.active_plan_id = "plan-basic"
        self.user_quota = UserQuota(daily_remaining=5, monthly_remaining=50, bonus_remaining=0)
        self.user_active_plan_ids = {}
        self.user_quotas = {}
        self.orders = {}
        self.safety_policy = SafetyPolicy(id="", blocked_terms=[], copyright_notice="")
        self.audit_logs = []
        self._ensure_seed_data()

    def _ensure_seed_data(self) -> None:
        changed = False
        default_genre_configs = _default_genre_configs()
        if not self.templates:
            self.templates = _default_templates()
            for template in self.templates.values():
                self.save_template(template)
            changed = True
        if not self.genre_configs:
            self.genre_configs = default_genre_configs
            for config in self.genre_configs.values():
                self.save_genre_config(config)
            changed = True
        else:
            for value, default_config in default_genre_configs.items():
                existing = self.genre_configs.get(value)
                if existing is None:
                    self.save_genre_config(default_config)
                    changed = True
                    continue
                merged = _merge_genre_config(existing, default_config)
                if merged != existing:
                    self.save_genre_config(merged)
                    changed = True
        if not self.membership_plans:
            self.membership_plans = _default_membership_plans()
            for plan in self.membership_plans.values():
                self.save_membership_plan(plan)
            self.active_plan_id = "plan-basic"
            self.user_quota = UserQuota(daily_remaining=5, monthly_remaining=50, bonus_remaining=0)
            self.save_active_plan()
            self.save_quota()
            changed = True
        if not self.orders:
            self.orders = _default_orders()
            for order in self.orders.values():
                self.save_order(order)
            changed = True
        if not self.safety_policy.id:
            self.safety_policy = _default_safety_policy()
            self.save_safety_policy()
            changed = True
        if changed:
            self._load_all()

    def _load_all(self) -> None:
        self.projects = self._load_model_map(Project, "projects")
        self.foundation_tasks = self._load_model_map(ProjectFoundationTask, "foundation_tasks")
        self.templates = self._load_model_map(Template, "templates")
        self.genre_configs = self._load_model_map(GenreConfig, "genre_configs")
        self.membership_plans = self._load_model_map(MembershipPlan, "membership_plans")
        self.orders = self._load_model_map(Order, "orders")
        self.safety_policy = self._load_singleton(SafetyPolicy, "safety_policy")
        self.audit_logs = self._load_audit_logs()
        self.active_plan_id, self.user_quota, self.user_active_plan_ids, self.user_quotas = self._load_app_state()

    def _load_model_map(self, model_cls, table_name: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        with self._connect() as connection:
            rows = connection.execute(f"SELECT id, payload FROM {table_name} ORDER BY id").fetchall()
        loaded: dict[str, Any] = {}
        for row in rows:
            payload = json.loads(row["payload"])
            model = model_cls.model_validate(payload)
            loaded[row["id"]] = model
        return loaded

    def _load_singleton(self, model_cls, table_name: str):  # type: ignore[no-untyped-def]
        with self._connect() as connection:
            row = connection.execute(f"SELECT payload FROM {table_name} ORDER BY id LIMIT 1").fetchone()
        if not row:
            return model_cls(id="", blocked_terms=[], copyright_notice="")
        return model_cls.model_validate(json.loads(row["payload"]))

    def _load_audit_logs(self) -> list[AuditLog]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM audit_logs ORDER BY created_at, id").fetchall()
        return [AuditLog.model_validate(json.loads(row["payload"])) for row in rows]

    def _load_app_state(self) -> tuple[str, UserQuota, dict[str, str], dict[str, UserQuota]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, active_plan_id, free_remaining,
                       COALESCE(daily_remaining, 0) AS daily_remaining,
                       monthly_remaining,
                       COALESCE(bonus_remaining, free_remaining, 0) AS bonus_remaining,
                       COALESCE(last_daily_reset_at, '') AS last_daily_reset_at,
                       COALESCE(last_monthly_reset_at, '') AS last_monthly_reset_at
                FROM app_state
                ORDER BY id
                """
            ).fetchall()
        global_plan_id = "plan-basic"
        global_quota = UserQuota(daily_remaining=5, monthly_remaining=50, bonus_remaining=0)
        user_active_plan_ids: dict[str, str] = {}
        user_quotas: dict[str, UserQuota] = {}
        for row in rows:
            now_iso = datetime.now(timezone.utc).isoformat()
            quota = UserQuota(
                daily_remaining=int(row["daily_remaining"]),
                monthly_remaining=int(row["monthly_remaining"]),
                bonus_remaining=int(row["bonus_remaining"]),
                last_daily_reset_at=datetime.fromisoformat(row["last_daily_reset_at"] or now_iso),
                last_monthly_reset_at=datetime.fromisoformat(row["last_monthly_reset_at"] or now_iso),
            )
            if row["id"] == "default":
                global_plan_id = row["active_plan_id"]
                global_quota = quota
            else:
                user_active_plan_ids[row["id"]] = row["active_plan_id"]
                user_quotas[row["id"]] = quota
        return global_plan_id, global_quota, user_active_plan_ids, user_quotas

    def save_project(self, project: Project) -> None:
        self.projects[project.id] = project
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (project.id, json.dumps(project.model_dump(mode="json"), ensure_ascii=False)),
            )
            connection.commit()

    def save_foundation_task(self, task: ProjectFoundationTask) -> None:
        self.foundation_tasks[task.id] = task
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO foundation_tasks (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (task.id, json.dumps(task.model_dump(mode="json"), ensure_ascii=False)),
            )
            connection.commit()

    def delete_project(self, project_id: str) -> None:
        self.projects.pop(project_id, None)
        with self._connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            connection.commit()

    def save_template(self, template: Template) -> None:
        self.templates[template.id] = template
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO templates (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (template.id, json.dumps(template.model_dump(mode="json"), ensure_ascii=False)),
            )
            connection.commit()

    def save_genre_config(self, config: GenreConfig) -> None:
        self.genre_configs[config.value] = config
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO genre_configs (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (config.value, json.dumps(config.model_dump(mode="json"), ensure_ascii=False)),
            )
            connection.commit()

    def save_membership_plan(self, plan: MembershipPlan) -> None:
        self.membership_plans[plan.id] = plan
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO membership_plans (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (plan.id, json.dumps(plan.model_dump(mode="json"), ensure_ascii=False)),
            )
            connection.commit()

    def save_order(self, order: Order) -> None:
        self.orders[order.id] = order
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO orders (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (order.id, json.dumps(order.model_dump(mode="json"), ensure_ascii=False)),
            )
            connection.commit()

    def save_quota(self) -> None:
        self._save_app_state()

    def save_active_plan(self) -> None:
        self._save_app_state()

    def save_user_quota(self, user_id: str) -> None:
        self._save_app_state(user_id)

    def save_user_active_plan(self, user_id: str) -> None:
        self._save_app_state(user_id)

    def migrate_user_state_alias(self, canonical_user_id: str, legacy_user_key: str | None) -> None:
        legacy_key = (legacy_user_key or "").strip()
        if not legacy_key or legacy_key == canonical_user_id:
            return
        super().migrate_user_state_alias(canonical_user_id, legacy_key)
        self._save_app_state(canonical_user_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM app_state WHERE id = ?", (legacy_key,))
            connection.commit()

    def _save_app_state(self, user_id: str | None = None) -> None:
        if user_id:
            self.ensure_user_state(user_id)
            state_id = user_id
            active_plan_id = self.user_active_plan_ids[user_id]
            quota = self.user_quotas[user_id]
        else:
            state_id = "default"
            active_plan_id = self.active_plan_id
            quota = self.user_quota
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_state (
                    id, active_plan_id, free_remaining, daily_remaining, monthly_remaining, bonus_remaining,
                    last_daily_reset_at, last_monthly_reset_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE
                SET active_plan_id = excluded.active_plan_id,
                    free_remaining = excluded.free_remaining,
                    daily_remaining = excluded.daily_remaining,
                    monthly_remaining = excluded.monthly_remaining
                    ,bonus_remaining = excluded.bonus_remaining
                    ,last_daily_reset_at = excluded.last_daily_reset_at
                    ,last_monthly_reset_at = excluded.last_monthly_reset_at
                """,
                (
                    state_id,
                    active_plan_id,
                    quota.bonus_remaining,
                    quota.daily_remaining,
                    quota.monthly_remaining,
                    quota.bonus_remaining,
                    quota.last_daily_reset_at.isoformat(),
                    quota.last_monthly_reset_at.isoformat(),
                ),
            )
            connection.commit()

    def save_safety_policy(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO safety_policy (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    self.safety_policy.id,
                    json.dumps(self.safety_policy.model_dump(mode="json"), ensure_ascii=False),
                ),
            )
            connection.commit()

    def log(self, action: str, details: dict[str, object]) -> None:
        entry = AuditLog(id=new_id("log"), action=action, details=details)
        self.audit_logs.append(entry)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_logs (id, payload, created_at) VALUES (?, ?, ?)
                """,
                (
                    entry.id,
                    json.dumps(entry.model_dump(mode="json"), ensure_ascii=False),
                    entry.created_at.isoformat(),
                ),
            )
            connection.commit()


class PostgresStore(InMemoryStore):
    def __init__(self, database_url: str) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL app storage")
        self.database_url = database_url
        super().__init__()
        self._init_schema()
        self._load_all()
        self._ensure_seed_data()

    def _connect(self):
        connection = psycopg.connect(self.database_url)
        connection.row_factory = dict_row
        return connection

    def _init_schema(self) -> None:
        schema_path = os.path.join(os.path.dirname(__file__), "sql", "postgres_schema.sql")
        with open(schema_path, "r", encoding="utf-8") as file:
            statements = [part.strip() for part in file.read().split(";") if part.strip()]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            connection.commit()

    def _ensure_seed_data(self) -> None:
        changed = False
        default_genre_configs = _default_genre_configs()
        if not self.templates:
            self.templates = _default_templates()
            for template in self.templates.values():
                self.save_template(template)
            changed = True
        if not self.genre_configs:
            self.genre_configs = default_genre_configs
            for config in self.genre_configs.values():
                self.save_genre_config(config)
            changed = True
        else:
            for value, default_config in default_genre_configs.items():
                existing = self.genre_configs.get(value)
                if existing is None:
                    self.save_genre_config(default_config)
                    changed = True
                    continue
                merged = _merge_genre_config(existing, default_config)
                if merged != existing:
                    self.save_genre_config(merged)
                    changed = True
        if not self.membership_plans:
            self.membership_plans = _default_membership_plans()
            for plan in self.membership_plans.values():
                self.save_membership_plan(plan)
            self.active_plan_id = "plan-basic"
            self.user_quota = UserQuota(daily_remaining=5, monthly_remaining=50, bonus_remaining=0)
            self.save_active_plan()
            self.save_quota()
            changed = True
        if not self.orders:
            self.orders = _default_orders()
            for order in self.orders.values():
                self.save_order(order)
            changed = True
        if not self.safety_policy.id:
            self.safety_policy = _default_safety_policy()
            self.save_safety_policy()
            changed = True
        if changed:
            self._load_all()

    def _load_all(self) -> None:
        self.projects = self._load_projects()
        self.foundation_tasks = self._load_foundation_tasks()
        self.templates = self._load_templates()
        self.genre_configs = self._load_genre_configs()
        self.membership_plans = self._load_membership_plans()
        self.orders = self._load_orders()
        self.safety_policy = self._load_safety_policy()
        self.audit_logs = self._load_audit_logs()
        self.active_plan_id, self.user_quota, self.user_active_plan_ids, self.user_quotas = self._load_app_state()

    def _load_templates(self) -> dict[str, Template]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, owner_type, owner_user_id, owner_username, name, genre, genres, tags, style_rules, world_template,
                           character_template, outline_template, status, usage_count
                    FROM templates
                    ORDER BY id
                    """
                )
                rows = cursor.fetchall()
        return {
            row["id"]: Template(
                id=row["id"],
                owner_type=row["owner_type"],
                owner_user_id=row["owner_user_id"],
                owner_username=row["owner_username"],
                name=row["name"],
                genre=row["genre"],
                genres=list(row.get("genres") or []),
                tags=list(row["tags"] or []),
                style_rules=row["style_rules"],
                world_template=row["world_template"],
                character_template=row["character_template"],
                outline_template=row["outline_template"],
                status=row["status"],
                usage_count=int(row["usage_count"] or 0),
            )
            for row in rows
        }

    def _load_genre_configs(self) -> dict[str, GenreConfig]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT value, label, required_any, forbidden_any
                    FROM genre_configs
                    ORDER BY value
                    """
                )
                rows = cursor.fetchall()
        return {
            row["value"]: GenreConfig(
                value=row["value"],
                label=row["label"],
                required_any=list(row["required_any"] or []),
                forbidden_any=list(row["forbidden_any"] or []),
            )
            for row in rows
        }

    def _load_foundation_tasks(self) -> dict[str, ProjectFoundationTask]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, payload FROM foundation_tasks ORDER BY id")
                rows = cursor.fetchall()
        loaded: dict[str, ProjectFoundationTask] = {}
        for row in rows:
            payload = row["payload"]
            if isinstance(payload, str):
                parsed = json.loads(payload)
            else:
                parsed = dict(payload)
            task = ProjectFoundationTask.model_validate(parsed)
            loaded[row["id"]] = task
        return loaded

    def _load_membership_plans(self) -> dict[str, MembershipPlan]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, free_chapter_quota, monthly_quota, description FROM membership_plans ORDER BY id"
                )
                rows = cursor.fetchall()
        return {
            row["id"]: MembershipPlan(
                id=row["id"],
                name=row["name"],
                daily_free_chapters=row["free_chapter_quota"],
                monthly_free_chapters=row["monthly_quota"],
                description=row["description"],
            )
            for row in rows
        }

    def _load_orders(self) -> dict[str, Order]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, plan_id, amount, status, note FROM orders ORDER BY id")
                rows = cursor.fetchall()
        return {
            row["id"]: Order(
                id=row["id"],
                plan_id=row["plan_id"],
                amount=float(row["amount"]),
                status=row["status"],
                note=row["note"],
            )
            for row in rows
        }

    def _load_safety_policy(self) -> SafetyPolicy:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, blocked_terms, copyright_notice FROM safety_policies ORDER BY id LIMIT 1")
                row = cursor.fetchone()
        if not row:
            return SafetyPolicy(id="", blocked_terms=[], copyright_notice="")
        return SafetyPolicy(
            id=row["id"],
            blocked_terms=list(row["blocked_terms"] or []),
            copyright_notice=row["copyright_notice"],
        )

    def _load_audit_logs(self) -> list[AuditLog]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, action, details, created_at FROM audit_logs ORDER BY created_at, id")
                rows = cursor.fetchall()
        return [
            AuditLog(id=row["id"], action=row["action"], details=dict(row["details"] or {}), created_at=row["created_at"])
            for row in rows
        ]

    def _load_app_state(self) -> tuple[str, UserQuota, dict[str, str], dict[str, UserQuota]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, active_plan_id, free_remaining, monthly_remaining
                    FROM app_state
                    ORDER BY id
                    """
                )
                rows = cursor.fetchall()
        global_plan_id = "plan-basic"
        global_quota = UserQuota(daily_remaining=5, monthly_remaining=50, bonus_remaining=0)
        user_active_plan_ids: dict[str, str] = {}
        user_quotas: dict[str, UserQuota] = {}
        for row in rows:
            quota = UserQuota(
                daily_remaining=0,
                monthly_remaining=row["monthly_remaining"],
                bonus_remaining=row["free_remaining"],
            )
            if row["id"] == "default":
                global_plan_id = row["active_plan_id"]
                global_quota = quota
            else:
                user_active_plan_ids[row["id"]] = row["active_plan_id"]
                user_quotas[row["id"]] = quota
        return global_plan_id, global_quota, user_active_plan_ids, user_quotas

    def _load_projects(self) -> dict[str, Project]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT p.id, COALESCE(p.user_id, '') AS user_id, p.title, p.genre, p.genres, p.length_type, p.template_id, p.mode_default, p.summary,
                           p.created_at, p.updated_at, m.global_outline, m.character_cards, m.character_profiles,
                           m.relationship_states, m.world_rules, m.event_summary, m.story_beats, m.active_phase, m.chapter_summaries, m.timeline_nodes, m.foreshadow_threads, m.major_events,
                           m.fact_records,
                           m.latest_chapter_index
                    FROM projects p
                    JOIN project_memories m ON m.project_id = p.id
                    ORDER BY p.created_at, p.id
                    """
                )
                project_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT id, project_id, chapter_index, title, status, selected_option_id, final_draft_id,
                           needs_manual_review, confirmed_by_user, rewrite_count
                    FROM chapters
                    ORDER BY project_id, chapter_index
                    """
                )
                chapter_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT id, chapter_id, option_no, content, core_conflict, key_event, ending_hook,
                           score_plot, score_consistency, score_hook, score_phase_fit, phase_fit_hits, final_score, editor_comment, selected
                    FROM outline_options
                    ORDER BY chapter_id, option_no
                    """
                )
                option_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT id, chapter_id, revision_no, content, score_readability, score_tension,
                           score_consistency, final_score, issue_summary, conflict_alerts, selected
                    FROM chapter_drafts
                    ORDER BY chapter_id, revision_no
                    """
                )
                draft_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT id, project_id, start_chapter_index, requested_chapter_count, mode, status,
                           current_chapter_index, chapter_ids, created_at, finished_at
                    FROM chapter_tasks
                    ORDER BY project_id, created_at, id
                    """
                )
                task_rows = cursor.fetchall()

        options_by_chapter: dict[str, list[OutlineOption]] = {}
        for row in option_rows:
            options_by_chapter.setdefault(row["chapter_id"], []).append(
                OutlineOption(
                    id=row["id"],
                    option_no=row["option_no"],
                    content=row["content"],
                    core_conflict=row["core_conflict"],
                    key_event=row["key_event"],
                    ending_hook=row["ending_hook"],
                    score_plot=float(row["score_plot"]),
                    score_consistency=float(row["score_consistency"]),
                    score_hook=float(row["score_hook"]),
                    score_phase_fit=float(row["score_phase_fit"] or 0),
                    phase_fit_hits=list(row["phase_fit_hits"] or []),
                    final_score=float(row["final_score"]),
                    editor_comment=row["editor_comment"],
                    selected=row["selected"],
                )
            )

        drafts_by_chapter: dict[str, list[ChapterDraft]] = {}
        for row in draft_rows:
            drafts_by_chapter.setdefault(row["chapter_id"], []).append(
                ChapterDraft(
                    id=row["id"],
                    revision_no=row["revision_no"],
                    content=row["content"],
                    score_readability=float(row["score_readability"]),
                    score_tension=float(row["score_tension"]),
                    score_consistency=float(row["score_consistency"]),
                    final_score=float(row["final_score"]),
                    issue_summary=row["issue_summary"],
                    conflict_alerts=list(row["conflict_alerts"] or []),
                    selected=row["selected"],
                )
            )

        chapters_by_project: dict[str, list[Chapter]] = {}
        for row in chapter_rows:
            chapters_by_project.setdefault(row["project_id"], []).append(
                Chapter(
                    id=row["id"],
                    chapter_index=row["chapter_index"],
                    title=row["title"],
                    status=row["status"],
                    outline_options=options_by_chapter.get(row["id"], []),
                    selected_option_id=row["selected_option_id"],
                    drafts=drafts_by_chapter.get(row["id"], []),
                    final_draft_id=row["final_draft_id"],
                    needs_manual_review=row["needs_manual_review"],
                    confirmed_by_user=row["confirmed_by_user"],
                    rewrite_count=row["rewrite_count"],
                )
            )

        tasks_by_project: dict[str, list[ChapterTask]] = {}
        for row in task_rows:
            tasks_by_project.setdefault(row["project_id"], []).append(
                ChapterTask(
                    id=row["id"],
                    project_id=row["project_id"],
                    start_chapter_index=row["start_chapter_index"],
                    requested_chapter_count=row["requested_chapter_count"],
                    mode=TaskMode(row["mode"]),
                    status=TaskStatus(row["status"]),
                    current_chapter_index=row["current_chapter_index"],
                    chapter_ids=list(row["chapter_ids"] or []),
                    created_at=row["created_at"],
                    finished_at=row["finished_at"],
                )
            )

        projects: dict[str, Project] = {}
        for row in project_rows:
            projects[row["id"]] = Project(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                genre=row["genre"],
                genres=list(row.get("genres") or []),
                length_type=row["length_type"],
                template_id=row["template_id"],
                mode_default=row["mode_default"],
                summary=row["summary"],
                memory=ProjectMemory(
                    global_outline=row["global_outline"],
                    character_cards=list(row["character_cards"] or []),
                    character_profiles=list(row["character_profiles"] or []),
                    relationship_states=list(row["relationship_states"] or []),
                    world_rules=list(row["world_rules"] or []),
                    event_summary=list(row["event_summary"] or []),
                    story_beats=list(row.get("story_beats") or []),
                    active_phase=dict(row.get("active_phase") or {}),
                    chapter_summaries=list(row["chapter_summaries"] or []),
                    timeline_nodes=list(row["timeline_nodes"] or []),
                    foreshadow_threads=list(row["foreshadow_threads"] or []),
                    major_events=list(row["major_events"] or []),
                    fact_records=list(row["fact_records"] or []),
                    latest_chapter_index=row["latest_chapter_index"],
                ),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                chapters=chapters_by_project.get(row["id"], []),
                tasks=tasks_by_project.get(row["id"], []),
            )
        return projects

    def save_project(self, project: Project) -> None:
        self.projects[project.id] = project
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO projects (id, user_id, title, genre, genres, length_type, template_id, mode_default, summary, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET user_id = EXCLUDED.user_id,
                        title = EXCLUDED.title,
                        genre = EXCLUDED.genre,
                        genres = EXCLUDED.genres,
                        length_type = EXCLUDED.length_type,
                        template_id = EXCLUDED.template_id,
                        mode_default = EXCLUDED.mode_default,
                        summary = EXCLUDED.summary,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        project.id,
                        project.user_id,
                        project.title,
                        project.genre,
                        json.dumps(project.genres, ensure_ascii=False),
                        project.length_type,
                        project.template_id,
                        project.mode_default.value,
                        project.summary,
                        project.created_at,
                        project.updated_at,
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO project_memories (
                        id, project_id, global_outline, character_cards, character_profiles, relationship_states, world_rules, event_summary,
                        story_beats, active_phase, chapter_summaries, timeline_nodes, foreshadow_threads, major_events, fact_records, latest_chapter_index, updated_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
                    ON CONFLICT (project_id) DO UPDATE
                    SET global_outline = EXCLUDED.global_outline,
                        character_cards = EXCLUDED.character_cards,
                        character_profiles = EXCLUDED.character_profiles,
                        relationship_states = EXCLUDED.relationship_states,
                        world_rules = EXCLUDED.world_rules,
                        event_summary = EXCLUDED.event_summary,
                        story_beats = EXCLUDED.story_beats,
                        active_phase = EXCLUDED.active_phase,
                        chapter_summaries = EXCLUDED.chapter_summaries,
                        timeline_nodes = EXCLUDED.timeline_nodes,
                        foreshadow_threads = EXCLUDED.foreshadow_threads,
                        major_events = EXCLUDED.major_events,
                        fact_records = EXCLUDED.fact_records,
                        latest_chapter_index = EXCLUDED.latest_chapter_index,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        f"memory_{project.id}",
                        project.id,
                        project.memory.global_outline,
                        json.dumps(project.memory.character_cards, ensure_ascii=False),
                        json.dumps(project.memory.character_profiles, ensure_ascii=False),
                        json.dumps(project.memory.relationship_states, ensure_ascii=False),
                        json.dumps(project.memory.world_rules, ensure_ascii=False),
                        json.dumps(project.memory.event_summary, ensure_ascii=False),
                        json.dumps(project.memory.story_beats, ensure_ascii=False),
                        json.dumps(project.memory.active_phase, ensure_ascii=False),
                        json.dumps(project.memory.chapter_summaries, ensure_ascii=False),
                        json.dumps(project.memory.timeline_nodes, ensure_ascii=False),
                        json.dumps(project.memory.foreshadow_threads, ensure_ascii=False),
                        json.dumps(project.memory.major_events, ensure_ascii=False),
                        json.dumps(project.memory.fact_records, ensure_ascii=False),
                        project.memory.latest_chapter_index,
                        project.updated_at,
                    ),
                )
                cursor.execute("DELETE FROM outline_options WHERE chapter_id IN (SELECT id FROM chapters WHERE project_id = %s)", (project.id,))
                cursor.execute("DELETE FROM chapter_drafts WHERE chapter_id IN (SELECT id FROM chapters WHERE project_id = %s)", (project.id,))
                cursor.execute("DELETE FROM chapters WHERE project_id = %s", (project.id,))
                cursor.execute("DELETE FROM chapter_tasks WHERE project_id = %s", (project.id,))
                for chapter in project.chapters:
                    cursor.execute(
                        """
                        INSERT INTO chapters (id, project_id, chapter_index, title, status, selected_option_id, final_draft_id, needs_manual_review, confirmed_by_user, rewrite_count, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                        """,
                        (
                            chapter.id,
                            project.id,
                            chapter.chapter_index,
                            chapter.title,
                            chapter.status.value,
                            chapter.selected_option_id,
                            chapter.final_draft_id,
                            chapter.needs_manual_review,
                            chapter.confirmed_by_user,
                            chapter.rewrite_count,
                            project.updated_at,
                        ),
                    )
                    for option in chapter.outline_options:
                        cursor.execute(
                            """
                            INSERT INTO outline_options (
                                id, chapter_id, option_no, content, core_conflict, key_event, ending_hook,
                                score_plot, score_consistency, score_hook, score_phase_fit, phase_fit_hits, final_score, editor_comment, selected
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                            """,
                            (
                                option.id,
                                chapter.id,
                                option.option_no,
                                option.content,
                                option.core_conflict,
                                option.key_event,
                                option.ending_hook,
                                option.score_plot,
                                option.score_consistency,
                                option.score_hook,
                                option.score_phase_fit,
                                json.dumps(option.phase_fit_hits, ensure_ascii=False),
                                option.final_score,
                                option.editor_comment,
                                option.selected,
                            ),
                        )
                    for draft in chapter.drafts:
                        cursor.execute(
                            """
                        INSERT INTO chapter_drafts (id, chapter_id, revision_no, content, score_readability, score_tension, score_consistency, final_score, issue_summary, conflict_alerts, selected, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
                        """,
                        (
                            draft.id,
                            chapter.id,
                            draft.revision_no,
                                draft.content,
                                draft.score_readability,
                                draft.score_tension,
                            draft.score_consistency,
                            draft.final_score,
                            draft.issue_summary,
                            json.dumps(draft.conflict_alerts, ensure_ascii=False),
                            draft.selected,
                        ),
                    )
                for task in project.tasks:
                    cursor.execute(
                        """
                        INSERT INTO chapter_tasks (id, project_id, start_chapter_index, requested_chapter_count, mode, status, current_chapter_index, quota_cost, chapter_ids, created_at, finished_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                        """,
                        (
                            task.id,
                            project.id,
                            task.start_chapter_index,
                            task.requested_chapter_count,
                            task.mode.value,
                            task.status.value,
                            task.current_chapter_index,
                            task.requested_chapter_count,
                            json.dumps(task.chapter_ids, ensure_ascii=False),
                            task.created_at,
                            task.finished_at,
                        ),
                    )
            connection.commit()

    def save_template(self, template: Template) -> None:
        self.templates[template.id] = template
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO templates (id, owner_type, owner_user_id, owner_username, name, genre, genres, tags, style_rules, world_template, character_template, outline_template, status, usage_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET owner_type = EXCLUDED.owner_type,
                        owner_user_id = EXCLUDED.owner_user_id,
                        owner_username = EXCLUDED.owner_username,
                        name = EXCLUDED.name,
                        genre = EXCLUDED.genre,
                        genres = EXCLUDED.genres,
                        tags = EXCLUDED.tags,
                        style_rules = EXCLUDED.style_rules,
                        world_template = EXCLUDED.world_template,
                        character_template = EXCLUDED.character_template,
                        outline_template = EXCLUDED.outline_template,
                        status = EXCLUDED.status,
                        usage_count = EXCLUDED.usage_count
                    """,
                    (
                        template.id,
                        template.owner_type,
                        template.owner_user_id,
                        template.owner_username,
                        template.name,
                        template.genre,
                        json.dumps(template.genres, ensure_ascii=False),
                        json.dumps(template.tags, ensure_ascii=False),
                        template.style_rules,
                        template.world_template,
                        template.character_template,
                        template.outline_template,
                        template.status,
                        template.usage_count,
                    ),
                )
            connection.commit()

    def save_genre_config(self, config: GenreConfig) -> None:
        self.genre_configs[config.value] = config
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO genre_configs (value, label, required_any, forbidden_any)
                    VALUES (%s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (value) DO UPDATE
                    SET label = EXCLUDED.label,
                        required_any = EXCLUDED.required_any,
                        forbidden_any = EXCLUDED.forbidden_any
                    """,
                    (
                        config.value,
                        config.label,
                        json.dumps(config.required_any, ensure_ascii=False),
                        json.dumps(config.forbidden_any, ensure_ascii=False),
                    ),
                )
            connection.commit()

    def save_foundation_task(self, task: ProjectFoundationTask) -> None:
        self.foundation_tasks[task.id] = task
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO foundation_tasks (id, payload)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload
                    """,
                    (task.id, json.dumps(task.model_dump(mode="json"), ensure_ascii=False)),
                )
            connection.commit()

    def delete_project(self, project_id: str) -> None:
        self.projects.pop(project_id, None)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
                cursor.execute("DELETE FROM project_memories WHERE project_id = %s", (project_id,))
                cursor.execute("DELETE FROM chapter_drafts WHERE chapter_id IN (SELECT id FROM chapters WHERE project_id = %s)", (project_id,))
                cursor.execute("DELETE FROM outline_options WHERE chapter_id IN (SELECT id FROM chapters WHERE project_id = %s)", (project_id,))
                cursor.execute("DELETE FROM chapters WHERE project_id = %s", (project_id,))
                cursor.execute("DELETE FROM chapter_tasks WHERE project_id = %s", (project_id,))
            connection.commit()

    def save_membership_plan(self, plan: MembershipPlan) -> None:
        self.membership_plans[plan.id] = plan
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO membership_plans (id, name, free_chapter_quota, monthly_quota, description)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET name = EXCLUDED.name,
                        free_chapter_quota = EXCLUDED.free_chapter_quota,
                        monthly_quota = EXCLUDED.monthly_quota,
                        description = EXCLUDED.description
                    """,
                    (plan.id, plan.name, plan.daily_free_chapters, plan.monthly_free_chapters, plan.description),
                )
            connection.commit()

    def save_order(self, order: Order) -> None:
        self.orders[order.id] = order
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO orders (id, plan_id, amount, status, note)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET plan_id = EXCLUDED.plan_id,
                        amount = EXCLUDED.amount,
                        status = EXCLUDED.status,
                        note = EXCLUDED.note
                    """,
                    (order.id, order.plan_id, order.amount, order.status, order.note),
                )
            connection.commit()

    def save_quota(self) -> None:
        self._upsert_app_state()

    def save_active_plan(self) -> None:
        self._upsert_app_state()

    def save_user_quota(self, user_id: str) -> None:
        self._upsert_app_state(user_id)

    def save_user_active_plan(self, user_id: str) -> None:
        self._upsert_app_state(user_id)

    def migrate_user_state_alias(self, canonical_user_id: str, legacy_user_key: str | None) -> None:
        legacy_key = (legacy_user_key or "").strip()
        if not legacy_key or legacy_key == canonical_user_id:
            return
        super().migrate_user_state_alias(canonical_user_id, legacy_key)
        self._upsert_app_state(canonical_user_id)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM app_state WHERE id = %s", (legacy_key,))
            connection.commit()

    def _upsert_app_state(self, user_id: str | None = None) -> None:
        if user_id:
            self.ensure_user_state(user_id)
            state_id = user_id
            active_plan_id = self.user_active_plan_ids[user_id]
            quota = self.user_quotas[user_id]
        else:
            state_id = "default"
            active_plan_id = self.active_plan_id
            quota = self.user_quota
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO app_state (id, active_plan_id, free_remaining, monthly_remaining, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET active_plan_id = EXCLUDED.active_plan_id,
                        free_remaining = EXCLUDED.free_remaining,
                        monthly_remaining = EXCLUDED.monthly_remaining,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (state_id, active_plan_id, quota.bonus_remaining, quota.monthly_remaining),
                )
            connection.commit()

    def save_safety_policy(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO safety_policies (id, blocked_terms, copyright_notice)
                    VALUES (%s, %s::jsonb, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET blocked_terms = EXCLUDED.blocked_terms,
                        copyright_notice = EXCLUDED.copyright_notice
                    """,
                    (
                        self.safety_policy.id,
                        json.dumps(self.safety_policy.blocked_terms, ensure_ascii=False),
                        self.safety_policy.copyright_notice,
                    ),
                )
            connection.commit()

    def log(self, action: str, details: dict[str, object]) -> None:
        entry = AuditLog(id=new_id("log"), action=action, details=details)
        self.audit_logs.append(entry)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO audit_logs (id, action, details, created_at)
                    VALUES (%s, %s, %s::jsonb, %s)
                    """,
                    (entry.id, entry.action, json.dumps(entry.details, ensure_ascii=False), entry.created_at),
                )
            connection.commit()


def build_store():
    backend = os.getenv("APP_STORAGE_BACKEND", "").strip().lower()
    database_url = os.getenv("APP_DATABASE_URL", "").strip() or os.getenv("AUTH_DATABASE_URL", "").strip()
    if backend == "sqlite":
        return SqliteStore()
    if database_url:
        return PostgresStore(database_url)
    raise RuntimeError(
        "PostgreSQL storage is required by default. Set APP_DATABASE_URL or AUTH_DATABASE_URL. "
        "Use APP_STORAGE_BACKEND=sqlite only for explicit local/test fallback."
    )


store = build_store()
