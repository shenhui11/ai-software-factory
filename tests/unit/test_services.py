from apps.backend.models import ChapterTransformRequest, ProjectCreate, ProjectFoundationRequest, TaskCreateRequest, TaskMode, Template
from apps.backend.services import DomainError, NovelService
from apps.backend.store import APP_BUSINESS_TIMEZONE, InMemoryStore, SqliteStore
from datetime import datetime, timedelta, timezone


def make_service() -> NovelService:
    return NovelService(InMemoryStore())


class FakeAgentRunner:
    def __init__(self) -> None:
        self.expand_calls: list[tuple[str, str]] = []
        self.rewrite_calls: list[tuple[str, str]] = []
        self.outline_calls: list[tuple[str, int]] = []
        self.draft_calls: list[tuple[str, int, int]] = []
        self.review_calls: list[tuple[str, int, int]] = []

    def generate_outline_options(self, project, chapter_index):  # type: ignore[no-untyped-def]
        self.outline_calls.append((project.id, chapter_index))
        return type(
            "OutlineResult",
            (),
            {
                "options": [
                    {
                        "option_no": 1,
                        "content": "AI 方案 1",
                        "core_conflict": "冲突 1",
                        "key_event": "事件 1",
                        "ending_hook": "钩子 1",
                        "score_plot": 8.1,
                        "score_consistency": 8.0,
                        "score_hook": 8.2,
                        "final_score": 8.1,
                        "editor_comment": "点评 1",
                    },
                    {
                        "option_no": 2,
                        "content": "AI 方案 2",
                        "core_conflict": "冲突 2",
                        "key_event": "事件 2",
                        "ending_hook": "钩子 2",
                        "score_plot": 8.7,
                        "score_consistency": 8.6,
                        "score_hook": 8.8,
                        "final_score": 8.7,
                        "editor_comment": "点评 2",
                    },
                    {
                        "option_no": 3,
                        "content": "AI 方案 3",
                        "core_conflict": "冲突 3",
                        "key_event": "事件 3",
                        "ending_hook": "钩子 3",
                        "score_plot": 7.8,
                        "score_consistency": 7.9,
                        "score_hook": 7.7,
                        "final_score": 7.8,
                        "editor_comment": "点评 3",
                    },
                ],
                "source": "fake",
                "fallback": False,
            },
        )()

    def generate_draft(self, project, chapter, option, revision_no, previous_issues):  # type: ignore[no-untyped-def]
        self.draft_calls.append((project.id, chapter.chapter_index, revision_no))
        suffix = f" 第{revision_no}轮" if revision_no > 1 else ""
        return type("Result", (), {"text": f"AI 正文 {option.content}{suffix}", "source": "fake", "fallback": False})()

    def review_draft(self, project, chapter, option, draft_content, revision_no):  # type: ignore[no-untyped-def]
        self.review_calls.append((project.id, chapter.chapter_index, revision_no))
        if project.genre == "horror":
            scores = [7.4, 7.6, 7.7, 7.8, 7.85, 7.9]
            score = scores[revision_no - 1]
        else:
            score = 7.6 if revision_no == 1 else 8.4
        return type(
            "ReviewResult",
            (),
            {
                "score_readability": round(score - 0.1, 2),
                "score_tension": round(score, 2),
                "score_consistency": round(min(score + 0.1, 8.9), 2),
                "final_score": score,
                "issue_summary": "情绪爆点仍然偏弱，需要进一步强化。" if score < 8.0 else "已达到当前发布阈值。",
                "source": "fake",
                "fallback": False,
            },
        )()

    def generate_project_foundation(self, payload):  # type: ignore[no-untyped-def]
        return {
            "summary": payload.get("summary") or f"{payload['title']}的自动生成总纲",
            "character_cards": payload.get("character_cards") or ["主角", "对手"],
            "world_rules": payload.get("world_rules") or ["规则一", "规则二"],
            "event_summary": payload.get("event_summary") or ["事件一", "事件二"],
            "source": "fake",
            "fallback": False,
        }

    def expand_chapter(self, project, chapter, payload):  # type: ignore[no-untyped-def]
        self.expand_calls.append((project.id, chapter.id))
        return type("Result", (), {"text": "智能体扩写结果", "source": "fake", "fallback": False})()

    def rewrite_chapter(self, project, chapter, payload):  # type: ignore[no-untyped-def]
        self.rewrite_calls.append((project.id, chapter.id))
        return type("Result", (), {"text": "智能体重写结果", "source": "fake", "fallback": False})()


class FallbackDraftRunner(FakeAgentRunner):
    def generate_draft(self, project, chapter, option, revision_no, previous_issues):  # type: ignore[no-untyped-def]
        self.draft_calls.append((project.id, chapter.chapter_index, revision_no))
        return type(
            "Result",
            (),
            {"text": "内容生成失败，已返回兜底文本。", "source": "fake", "fallback": True},
        )()

    def review_draft(self, project, chapter, option, draft_content, revision_no):  # type: ignore[no-untyped-def]
        self.review_calls.append((project.id, chapter.chapter_index, revision_no))
        return type(
            "ReviewResult",
            (),
            {
                "score_readability": 8.0,
                "score_tension": 8.1,
                "score_consistency": 8.2,
                "final_score": 8.1,
                "issue_summary": "整体可读性稳定，情绪推进自然，但结尾钩子还可以更锋利。",
                "source": "fake",
                "fallback": True,
            },
        )()


class ConsistencyPenaltyRunner(FakeAgentRunner):
    def generate_draft(self, project, chapter, option, revision_no, previous_issues):  # type: ignore[no-untyped-def]
        self.draft_calls.append((project.id, chapter.chapter_index, revision_no))
        suffix = f" 第{revision_no}轮" if revision_no > 1 else ""
        return type("Result", (), {"text": f"无名场景推进{suffix}", "source": "fake", "fallback": False})()

    def review_draft(self, project, chapter, option, draft_content, revision_no):  # type: ignore[no-untyped-def]
        self.review_calls.append((project.id, chapter.chapter_index, revision_no))
        score = 8.2 if revision_no == 1 else 8.5
        return type(
            "ReviewResult",
            (),
            {
                "score_readability": 8.0,
                "score_tension": 8.1,
                "score_consistency": 8.2,
                "final_score": score,
                "issue_summary": "基础质量合格。",
                "source": "fake",
                "fallback": False,
            },
        )()


class ContextCaptureRunner(FakeAgentRunner):
    def __init__(self) -> None:
        super().__init__()
        self.outline_contexts: list[dict[str, object]] = []

    def generate_outline_options_with_context(self, project, chapter_index, context_packet):  # type: ignore[no-untyped-def]
        self.outline_contexts.append(context_packet)
        return self.generate_outline_options(project, chapter_index)


class RegressionDraftRunner(FakeAgentRunner):
    def generate_draft(self, project, chapter, option, revision_no, previous_issues):  # type: ignore[no-untyped-def]
        self.draft_calls.append((project.id, chapter.chapter_index, revision_no))
        if revision_no == 1:
            text = (
                "能量罩完全合拢，显示屏亮起同步进度条。"
                "第38次同步开始，进度条从0%跳到12%，又到20%。"
                "另一个林渊站在他对面，开口解释同步规则。"
            )
        else:
            text = (
                "林渊在白光牵引后的眩晕中醒来，意识到上一章的同步高位推进并没有结束。"
                "屏幕已经跳到76%，他只能咬牙承接回收流程，勉强抬手去摸身侧发烫的金属壁。"
            )
        return type("Result", (), {"text": text, "source": "fake", "fallback": False})()

    def review_draft(self, project, chapter, option, draft_content, revision_no):  # type: ignore[no-untyped-def]
        self.review_calls.append((project.id, chapter.chapter_index, revision_no))
        score = 8.5
        return type(
            "ReviewResult",
            (),
            {
                "score_readability": 8.4,
                "score_tension": 8.5,
                "score_consistency": 8.6,
                "final_score": score,
                "issue_summary": "基础质量合格。",
                "source": "fake",
                "fallback": False,
            },
        )()


def make_project(service: NovelService, genre: str = "fantasy") -> str:
    project = service.create_project(
        ProjectCreate(
            title="Test Novel",
            genre=genre,
            length_type="long",
            template_id="tpl-system-romance",
            summary="A summary",
            character_cards=["Hero"],
            world_rules=["Rule"],
            event_summary=["Event"],
            mode_default=TaskMode.manual,
        )
    )
    return project.id


def test_horror_project_hits_max_rewrites_and_manual_review() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service, genre="horror")
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    result = service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]
    assert result.status.value == "completed"
    assert len(chapter.drafts) == 6
    assert chapter.rewrite_count == 5
    assert chapter.needs_manual_review is True


def test_project_foundation_generation_fills_missing_fields() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    foundation = service.generate_project_foundation(
        ProjectFoundationRequest(
            title="星海回声",
            genre="sci_fi",
            length_type="long",
            template_id="tpl-system-romance",
            summary="",
            character_cards=[],
            world_rules=[],
            event_summary=[],
        )
    )

    assert foundation["summary"]
    assert foundation["character_cards"]
    assert foundation["world_rules"]
    assert foundation["event_summary"]
    assert foundation["story_beats"]
    assert foundation["active_phase"]


def test_project_foundation_generation_merges_existing_and_generated_fields() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    foundation = service.generate_project_foundation(
        ProjectFoundationRequest(
            title="雾海长灯",
            genre="fantasy",
            length_type="long",
            template_id="tpl-system-romance",
            summary="失忆领航员在迷雾海寻找失落灯塔。",
            character_cards=["领航员"],
            world_rules=["迷雾会吞噬方向感"],
            event_summary=["灯塔曾在旧战争后熄灭"],
        )
    )

    assert foundation["summary"] == "失忆领航员在迷雾海寻找失落灯塔。"
    assert foundation["character_cards"] == ["领航员"]
    assert foundation["world_rules"] == ["迷雾会吞噬方向感"]
    assert foundation["event_summary"] == ["灯塔曾在旧战争后熄灭"]


def test_project_foundation_preserves_existing_summary_against_fallback_defaults() -> None:
    service = NovelService(InMemoryStore())
    foundation = service.generate_project_foundation(
        ProjectFoundationRequest(
            title="万界锚点",
            genre="fantasy",
            length_type="long",
            template_id="tpl-system-romance",
            summary="用户自己写的总纲摘要。",
            character_cards=[],
            world_rules=[],
            event_summary=[],
        )
    )

    assert foundation["summary"] == "用户自己写的总纲摘要。"


def test_list_genres_includes_defaults_and_custom_template_genre() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    service.create_template(
        Template(
            id="tpl-custom",
            name="赛博志怪模板",
            genre="cyber_fantasy",
            style_rules="强化技术异化。",
            world_template="数据城寨",
            character_template="异能黑客",
            outline_template="异常入侵",
            status="draft",
            owner_type="user",
        )
    )

    genres = service.list_genres()

    assert any(item["value"] == "fantasy" for item in genres)
    assert any(item["value"] == "cyber_fantasy" for item in genres)


def test_create_project_saves_exact_form_values_without_backend_autofill() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project = service.create_project(
        ProjectCreate(
            title="雾城档案",
            genre="suspense",
            length_type="long",
            template_id="tpl-system-romance",
            summary="",
            character_cards=[],
            world_rules=[],
            event_summary=[],
            mode_default=TaskMode.manual,
        )
    )

    assert project.summary == ""
    assert project.memory.character_cards == []
    assert project.memory.character_profiles == []
    assert project.memory.relationship_states == []
    assert project.memory.world_rules == []
    assert project.memory.event_summary == []


def test_create_project_accepts_empty_template_id() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project = service.create_project(
        ProjectCreate(
            title="无模板项目",
            genre="fantasy",
            length_type="long",
            template_id="",
            summary="用户自己的摘要",
            character_cards=["主角"],
            world_rules=["规则"],
            event_summary=["事件"],
            mode_default=TaskMode.manual,
        )
    )

    assert project.id
    assert project.summary == "用户自己的摘要"
    assert project.memory.character_cards == ["主角"]
    assert project.memory.story_beats
    assert project.memory.active_phase


def test_create_project_increments_template_usage_count() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    before = service.db.templates["tpl-system-romance"].usage_count

    service.create_project(
        ProjectCreate(
            title="群星回廊",
            genre="fantasy",
            length_type="long",
            template_id="tpl-system-romance",
            summary="",
            character_cards=[],
            world_rules=[],
            event_summary=[],
            mode_default=TaskMode.manual,
        )
    )

    assert service.db.templates["tpl-system-romance"].usage_count == before + 1


def test_list_templates_keeps_user_templates_visible_when_user_id_changes_but_username_matches() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    template = Template(
        id="tpl-user-owned",
        name="我的悬疑模板",
        genre="suspense",
        tags=["悬疑"],
        style_rules="强化反转",
        world_template="雨夜旧城",
        character_template="调查者与线人",
        outline_template="异常出现、追查升级、真相反转",
        status="draft",
        owner_type="user",
    )

    service.create_template("user_old_id", template, "alice")
    visible = service.list_templates("user_new_id", "alice")

    assert any(item.id == "tpl-user-owned" for item in visible)


def test_update_template_accepts_owner_username_fallback_and_refreshes_owner_user_id() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    template = Template(
        id="tpl-user-edit",
        name="旧模板",
        genre="fantasy",
        tags=["冒险"],
        style_rules="旧风格",
        world_template="旧世界",
        character_template="旧角色",
        outline_template="旧大纲",
        status="draft",
        owner_type="user",
        owner_user_id="user_old_id",
        owner_username="alice",
    )
    service.db.save_template(template)

    updated = service.update_template("user_new_id", "tpl-user-edit", {"name": "新模板"}, "alice")

    assert updated.name == "新模板"
    assert updated.owner_user_id == "user_new_id"
    assert updated.owner_username == "alice"


def test_final_draft_keeps_highest_score() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]
    final_draft = next(draft for draft in chapter.drafts if draft.selected)
    assert final_draft.final_score == max(draft.final_score for draft in chapter.drafts)


def test_consistency_penalty_below_threshold_triggers_additional_rewrite() -> None:
    service = NovelService(InMemoryStore(), agent_runner=ConsistencyPenaltyRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )

    service.run_task(project_id, task.id)

    chapter = service.get_project(project_id).chapters[0]
    assert len(chapter.drafts) == 2
    assert chapter.drafts[0].final_score < 8.0
    assert chapter.drafts[1].final_score >= 8.0


def test_context_packet_retrieves_relevant_non_recent_memory() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    project = service.get_project(project_id)
    project.memory.character_cards = ["莉娜", "罗文", "沈夜"]
    project.memory.character_profiles = [
        {"name": "莉娜", "anchor": "冷静法师", "current_state": "调查月蚀遗迹", "current_goal": "查清遗迹异动", "last_seen_chapter_index": 7},
        {"name": "罗文", "anchor": "执拗王子", "current_state": "追查钟楼密档", "current_goal": "找出王都档案真相", "last_seen_chapter_index": 2},
        {"name": "沈夜", "anchor": "隐忍档案官", "current_state": "留守档案馆", "current_goal": "监控局势", "last_seen_chapter_index": 8},
    ]
    project.memory.relationship_states = [
        {"source": "莉娜", "target": "沈夜", "status": "互相提防", "chapter_index": 8, "reason": "立场不同"},
        {"source": "罗文", "target": "莉娜", "status": "秘密结盟", "chapter_index": 2, "reason": "共同调查钟楼密档"},
    ]
    project.memory.chapter_summaries = [
        {"chapter_index": 2, "summary": "罗文在王都钟楼发现被篡改的密档", "outline_hook": "密档里藏着先王遗令", "draft_excerpt": "罗文独自潜入钟楼"},
        {"chapter_index": 6, "summary": "沈夜封存旧档案", "outline_hook": "馆内有人删改记录", "draft_excerpt": "夜色压住长廊"},
        {"chapter_index": 8, "summary": "莉娜处理边境骚动", "outline_hook": "边境火种未灭", "draft_excerpt": "边境风雪不断"},
    ]
    project.memory.timeline_nodes = [
        {"sequence_no": 2, "chapter_index": 2, "summary": "钟楼密档暴露先王遗令", "participants": ["罗文", "莉娜"], "source": "chapter_2"},
        {"sequence_no": 8, "chapter_index": 8, "summary": "边境出现新的骚动", "participants": ["莉娜"], "source": "chapter_8"},
    ]
    project.memory.major_events = [
        {"chapter_index": 2, "summary": "钟楼密档暴露先王遗令", "impact": "罗文怀疑王都内廷"},
        {"chapter_index": 8, "summary": "边境出现新的骚动", "impact": "莉娜被迫离开王都"},
    ]
    project.memory.fact_records = [
        {"chapter_index": 2, "fact_type": "draft_fact", "subject": "罗文", "summary": "罗文在钟楼确认密档被人为篡改", "keywords": ["罗文", "钟楼", "密档", "篡改"], "source": "draft_sentence"},
        {"chapter_index": 8, "fact_type": "draft_fact", "subject": "莉娜", "summary": "莉娜压制边境骚动", "keywords": ["莉娜", "边境", "骚动"], "source": "draft_sentence"},
    ]
    project.memory.foreshadow_threads = [
        {"title": "钟楼密档", "introduced_chapter_index": 2, "status": "open", "latest_progress_note": "罗文怀疑还有第二份密档"},
        {"title": "边境火种", "introduced_chapter_index": 8, "status": "open", "latest_progress_note": "莉娜担心战火重燃"},
    ]

    packet = service._build_context_packet(project, 9, "罗文继续调查王都钟楼密档，确认先王遗令是否被伪造")

    assert packet["retrieval_focus"]["characters"] == ["罗文"]
    assert any(item["chapter_index"] == 2 for item in packet["chapter_summaries"])
    assert any(item["chapter_index"] == 2 for item in packet["timeline_nodes"])
    assert any(item["chapter_index"] == 2 for item in packet["major_events"])
    assert any(item["subject"] == "罗文" for item in packet["fact_records"])
    assert any(item["source"] == "罗文" or item["target"] == "罗文" for item in packet["relationship_states"])
    assert any(item["title"] == "钟楼密档" for item in packet["active_foreshadows"])


def test_outline_generation_receives_retrieved_context_packet() -> None:
    runner = ContextCaptureRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    project = service.get_project(project_id)
    project.memory.character_cards = ["Hero", "Rival", "Archivist"]
    project.memory.chapter_summaries = [
        {"chapter_index": 1, "summary": "Rival hides the archive key", "outline_hook": "The key opens the sealed vault", "draft_excerpt": "Hero notices the missing key"},
    ]
    project.memory.foreshadow_threads = [
        {"title": "archive key", "introduced_chapter_index": 1, "status": "open", "latest_progress_note": "Rival still controls the key"},
    ]

    service._build_outline_options(project, 2)

    assert runner.outline_contexts
    captured = runner.outline_contexts[0]
    assert "retrieval_focus" in captured
    assert "story_beats" in captured
    assert "active_phase" in captured
    assert captured["chapter_summaries"]
    assert "fact_records" in captured
    assert captured["style_rules"] == "情绪推进细腻，节奏温暖克制"
    assert captured["world_template"] == "现代都市背景"
    assert captured["character_template"] == "目标冲突明显的男女主"
    assert captured["outline_template"] == "相遇、碰撞、揭露、和解"


def test_outline_generation_includes_latest_scene_bridge_and_constraints() -> None:
    runner = ContextCaptureRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    project = service.get_project(project_id)
    project.memory.chapter_summaries = [
        {
            "chapter_index": 3,
            "summary": "同步已经压到高位",
            "outline_hook": "欢迎回来，林渊",
            "draft_excerpt": "白光吞没视野",
            "last_scene_excerpt": "屏幕上的进度条跳到了72%。然后他的意识被彻底拽进了白光里。",
            "last_scene_summary": "第38次同步已推进到72%，林渊被白光拖入更深层意识。",
            "continuity_state": {"max_progress_percent": 72, "has_forced_consciousness_pull": True},
            "hard_constraints": ["同步/进度类事件已推进至至少 72% ，后续不可无解释重置为更低阶段。"],
        }
    ]

    service._build_outline_options(project, 4)

    captured = runner.outline_contexts[0]
    assert captured["latest_scene_bridge"]["previous_chapter_index"] == 3
    assert "72%" in captured["latest_scene_bridge"]["last_scene_excerpt"]
    assert captured["latest_scene_bridge"]["continuity_state"]["max_progress_percent"] == 72
    assert captured["latest_scene_bridge"]["hard_constraints"]
    assert any("72%" in item for item in captured["consistency_rules"])


def test_context_packet_forces_previous_chapter_snapshot_into_outline_context() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    project = service.get_project(project_id)
    project.memory.chapter_summaries = [
        {
            "chapter_index": 3,
            "summary": "同步推进",
            "outline_hook": "中年男人现身",
            "draft_excerpt": "白光吞没了视野",
            "last_scene_excerpt": "进度：72%。中年男人说这是第39次躺进回收舱，然后他的意识被彻底拽进了白光里。",
            "last_scene_summary": "同步推进至72%，中年男人揭示第39次回收，林渊被拖入白光。",
            "continuity_state": {"max_progress_percent": 72, "has_forced_consciousness_pull": True},
            "hard_constraints": [
                "同步/进度类事件已推进至至少 72% ，后续不可无解释重置为更低阶段。",
                "上一章结尾已出现强制意识牵引或失能状态，下一章必须解释恢复过程。",
            ],
        }
    ]

    packet = service._build_context_packet(project, 4, "第4章继续同步后的结果", action="chapter_outlines")

    previous_summary = [item for item in packet["chapter_summaries"] if item["chapter_index"] == 3]
    assert previous_summary
    assert "72%" in previous_summary[0]["last_scene_excerpt"]
    assert "第39次" in previous_summary[0]["last_scene_summary"]


def test_style_checks_flag_summary_tone_and_repeated_connectors() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    text = (
        "与此同时，他站在门口，没有进去。\n"
        "然而，他也没有离开。\n"
        "紧接着，他看见灯影晃了一下。\n"
        "下一刻，他忽然明白了什么。\n"
        "这一切都说明，他已经被卷进去了。\n"
        "某种意义上，这也是命运给出的回答。"
    )

    alerts = service._run_style_checks(text)

    assert any("总结腔" in item for item in alerts)


def test_outline_genre_fit_penalizes_fantasy_option_with_lab_thriller_signals() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())

    score, alerts = service._score_outline_genre_fit(
        "fantasy",
        {
            "content": "主角在实验室档案间调取病历，准备去主控室破解控制台。",
            "core_conflict": "实验员准备启动回收舱。",
            "key_event": "数据库给出新的受试者编号。",
            "ending_hook": "电子音提示回收程序开始。",
        },
    )

    assert score < 8.0
    assert alerts
    assert any("题材串台" in item or "题材方向偏移" in item for item in alerts)


def test_genre_checks_flag_fantasy_draft_that_lacks_fantasy_signals() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service, genre="fantasy")
    project = service.get_project(project_id)
    option = OutlineOption(
        id="opt-1",
        option_no=1,
        content="主角在实验室追查档案。",
        core_conflict="他必须从控制台拿到权限。",
        key_event="数据库回传异常样本记录。",
        ending_hook="主控室的大门即将关闭。",
        score_plot=8.0,
        score_consistency=8.0,
        score_hook=8.0,
        score_phase_fit=8.0,
        phase_fit_hits=[],
        final_score=8.0,
        editor_comment="",
    )

    alerts = service._run_genre_checks(
        project,
        option,
        "林渊冲进实验室，翻开病历，又在控制台前调取数据库记录，准备进入主控室。",
    )

    assert alerts
    assert any("题材主信号不足" in item for item in alerts)
    assert any("题材串台" in item or "题材方向偏移" in item for item in alerts)


def test_update_chapter_draft_applies_genre_penalty_to_fantasy_lab_text() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service, genre="fantasy")
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    project = service.get_project(project_id)
    chapter = project.chapters[0]

    updated = service.update_chapter_draft(
        project_id,
        chapter.id,
        "林渊冲进实验室，调出病历和数据库，在控制台前等待主控室解锁，实验员的脚步声越来越近。",
    )
    selected = next(draft for draft in updated.drafts if draft.selected)

    assert "题材提醒：" in selected.issue_summary
    assert selected.final_score < 8.4


def test_scene_regression_penalty_triggers_additional_rewrite() -> None:
    service = NovelService(InMemoryStore(), agent_runner=RegressionDraftRunner())
    project_id = make_project(service)
    project = service.get_project(project_id)
    project.memory.chapter_summaries = [
        {
            "chapter_index": 1,
            "summary": "同步高位推进",
            "outline_hook": "回收舱即将闭锁",
            "draft_excerpt": "白光贴上眼皮",
            "last_scene_excerpt": "进度：72%。然后他的意识被彻底拽进了那片白光里。",
            "last_scene_summary": "同步已经推进至72%，林渊失去外部行动能力。",
            "continuity_state": {
                "max_progress_percent": 72,
                "has_forced_consciousness_pull": True,
                "has_non_interruptible_process": True,
            },
            "hard_constraints": [
                "同步/进度类事件已推进至至少 72% ，后续不可无解释重置为更低阶段。",
                "上一章结尾已出现强制意识牵引或失能状态，下一章必须解释恢复过程。",
            ],
        }
    ]
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=2),
    )

    service.run_task(project_id, task.id)

    chapter = service.get_project(project_id).chapters[0]
    assert len(chapter.drafts) == 2
    assert chapter.drafts[0].final_score < 8.0
    assert "时间线回卷" in chapter.drafts[0].issue_summary or "进度回退" in chapter.drafts[0].issue_summary
    assert chapter.drafts[1].final_score >= 8.0


def test_style_alerts_reduce_draft_score_and_merge_into_issue_summary() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    project = service.get_project(project_id)
    chapter = project.chapters[0]

    updated = service.update_chapter_draft(
        project_id,
        chapter.id,
        (
            "与此同时，他没有说话。\n"
            "然而，他也没有退开。\n"
            "紧接着，风从窗缝里灌进来。\n"
            "下一刻，他像是忽然懂了。\n"
            "这一切都说明，他终于走到了必须表态的时候。\n"
            "某种意义上，这也是无法回头的一步。"
        ),
    )
    selected = next(draft for draft in updated.drafts if draft.selected)

    assert "表达提醒：" in selected.issue_summary
    assert selected.final_score < 8.4


def test_regenerate_outlines_includes_optional_user_idea_in_context() -> None:
    runner = ContextCaptureRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]

    service.regenerate_chapter_outlines("", project_id, chapter.id, "希望这一章增加一次公开对峙，并埋下新的误导线索")

    assert runner.outline_contexts
    captured = runner.outline_contexts[-1]
    assert captured["user_idea"] == "希望这一章增加一次公开对峙，并埋下新的误导线索"
    assert "用户补充想法" in captured["retrieval_focus"]["query_text"]


def test_update_chapter_draft_writes_fact_records() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    project = service.get_project(project_id)
    project.memory.character_cards = ["Hero", "Rival"]
    chapter = project.chapters[0]

    service.update_chapter_draft(project_id, chapter.id, "Hero 在王都钟楼发现 Rival 篡改了密档。Hero 决定继续追查。")

    updated_project = service.get_project(project_id)
    facts = [item for item in updated_project.memory.fact_records if item.get("chapter_index") == 1]
    assert facts
    assert any(item["fact_type"] == "draft_fact" for item in facts)
    assert any(item["subject"] == "Hero" for item in facts)


def test_update_chapter_draft_adds_fact_conflict_alert_to_issue_summary() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    project = service.get_project(project_id)
    project.memory.character_cards = ["Hero", "Rival"]
    project.memory.fact_records.append(
        {
            "chapter_index": 0,
            "fact_type": "relationship_shift",
            "subject": "Hero",
            "summary": "Hero 与 Rival 已经结盟",
            "keywords": ["Hero", "Rival", "结盟"],
            "source": "seed",
        }
    )
    chapter = project.chapters[0]

    updated = service.update_chapter_draft(project_id, chapter.id, "Hero 决定与 Rival 彻底决裂，并公开指责对方。")
    selected = next(draft for draft in updated.drafts if draft.selected)

    assert "设定冲突" in selected.issue_summary
    assert selected.conflict_alerts
    assert selected.conflict_alerts[0]["subject"] == "Hero"
    assert "结盟" in selected.conflict_alerts[0]["existing_fact"]


def test_sqlite_store_persists_project_and_memory_across_restart(tmp_path) -> None:
    db_path = tmp_path / "app.db"
    first_store = SqliteStore(str(db_path))
    service = NovelService(first_store, agent_runner=FakeAgentRunner())
    project = service.create_project(
        ProjectCreate(
            title="持久化测试",
            genre="fantasy",
            length_type="long",
            template_id="tpl-system-romance",
            summary="",
            character_cards=["Hero", "Rival"],
            world_rules=["Magic has a price"],
            event_summary=["The city fell"],
            mode_default=TaskMode.manual,
        )
    )
    task = service.create_task(
        project.id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project.id, task.id)

    restarted_store = SqliteStore(str(db_path))
    restored_project = restarted_store.projects[project.id]

    assert restored_project.title == "持久化测试"
    assert restored_project.chapters
    assert restored_project.memory.chapter_summaries
    assert restored_project.memory.fact_records


def test_sqlite_store_persists_user_template_visibility_across_restart(tmp_path) -> None:
    db_path = tmp_path / "app.db"
    first_store = SqliteStore(str(db_path))
    service = NovelService(first_store, agent_runner=FakeAgentRunner())
    template = Template(
        id="tpl-user-persisted",
        name="持久化模板",
        genre="fantasy",
        tags=["冒险"],
        style_rules="强化悬念",
        world_template="旧王都",
        character_template="主角与档案官",
        outline_template="发现、追查、反转",
        status="draft",
        owner_type="user",
    )

    service.create_template("user_001", template, "alice")

    restarted_store = SqliteStore(str(db_path))
    restarted_service = NovelService(restarted_store, agent_runner=FakeAgentRunner())
    visible = restarted_service.list_templates("user_001", "alice")

    assert any(item.id == "tpl-user-persisted" for item in visible)


def test_chapter_rewrite_returns_diff_and_consistency_note() -> None:
    runner = FakeAgentRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]
    result = service.rewrite_chapter(
        project_id,
        chapter.id,
        ChapterTransformRequest(instruction="强化冲突", chapter_content="Old text"),
    )
    assert runner.rewrite_calls == [(project_id, chapter.id)]
    assert result.updated == "智能体重写结果"
    assert result.diff
    assert "连贯" in result.consistency_note
    assert result.chapter_updated


def test_chapter_expand_returns_updated_chapter_content() -> None:
    runner = FakeAgentRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    project = service.get_project(project_id)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = project.chapters[0]
    final_draft = next(draft for draft in chapter.drafts if draft.selected)

    result = service.expand_chapter(
        project_id,
        chapter.id,
        ChapterTransformRequest(instruction="补充角色动作和环境反应", chapter_content=final_draft.content),
    )

    assert runner.expand_calls == [(project_id, chapter.id)]
    assert result.updated == "智能体扩写结果"
    assert result.chapter_updated
    assert "智能体扩写结果" in result.chapter_updated


def test_paragraph_transform_replaces_only_target_segment() -> None:
    runner = FakeAgentRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]

    result = service.rewrite_chapter(
        project_id,
        chapter.id,
        ChapterTransformRequest(
            instruction="精炼第一段",
            chapter_content="第一段\n第二段",
            paragraph="第一段",
        ),
    )

    assert runner.rewrite_calls == [(project_id, chapter.id)]
    assert result.updated == "智能体重写结果\n第二段"
    assert result.original == "第一段\n第二段"
    assert result.chapter_updated == "智能体重写结果\n第二段"


def test_remove_chapter_paragraph_returns_updated_chapter_content() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]

    result = service.remove_chapter_paragraph(
        project_id,
        chapter.id,
        ChapterTransformRequest(
            instruction="删除重复铺垫",
            chapter_content="第一段\n第二段",
            paragraph="第一段",
        ),
    )

    assert result.original == "第一段\n第二段"
    assert result.updated == "第二段"
    assert result.chapter_updated == "第二段"
    assert any(item["type"] == "removed" and item["text"] == "第一段" for item in result.diff)


def test_generated_chapter_updates_structured_memory() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    memory = service.get_project(project_id).memory

    assert memory.latest_chapter_index == 1
    assert memory.character_profiles
    assert any(item["appeared_chapter_indexes"] for item in memory.character_profiles)
    assert all("current_goal" in item for item in memory.character_profiles)
    assert memory.chapter_summaries
    assert memory.timeline_nodes
    assert memory.foreshadow_threads
    assert memory.major_events
    assert memory.story_beats
    assert memory.active_phase
    assert any(item["chapter_index"] == 1 for item in memory.major_events)


def test_legacy_project_without_story_beats_gets_compatible_defaults() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    project = service.db.projects[project_id]
    project.memory.story_beats = []
    project.memory.active_phase = {}

    restored = service.get_project(project_id)

    assert restored.memory.story_beats
    assert restored.memory.active_phase
    assert restored.memory.active_phase["status"] == "active"


def test_story_beats_roll_forward_after_stage_boundary() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=3, start_chapter_index=1),
    )

    service.run_task(project_id, task.id)
    project = service.get_project(project_id)

    assert project.memory.latest_chapter_index == 3
    assert project.memory.story_beats[0]["status"] == "completed"
    assert project.memory.active_phase["phase_index"] == 2


def test_chapter_title_can_be_updated_before_confirmation() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.manual, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]

    updated = service.update_chapter_title(project_id, chapter.id, "月蚀档案馆的来信")

    assert updated.title == "月蚀档案馆的来信"


def test_run_task_uses_agent_runner_for_chapter_generation() -> None:
    runner = FakeAgentRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )

    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]

    assert runner.outline_calls == [(project_id, 1)]
    assert runner.draft_calls == [(project_id, 1, 1), (project_id, 1, 2)]
    assert runner.review_calls == [(project_id, 1, 1), (project_id, 1, 2)]
    assert chapter.outline_options[1].content == "AI 方案 2"
    assert chapter.drafts[0].content == "AI 正文 AI 方案 2"


def test_fallback_draft_never_passes_review() -> None:
    runner = FallbackDraftRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )

    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]
    final_draft = next(draft for draft in chapter.drafts if draft.selected)

    assert final_draft.content == "内容生成失败，已返回兜底文本。"
    assert final_draft.final_score < 8.0
    assert chapter.needs_manual_review is True


def test_membership_plan_activation_changes_current_plan() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())

    plan = service.create_membership_plan("测试套餐", 6, 30, "用于测试切换")
    service.activate_membership_plan(plan.id)

    memberships = service.list_membership_plans()
    assert memberships["default_plan_id"] == plan.id
    assert any(item.id == plan.id for item in memberships["plans"])


def test_order_update_persists_status_and_note() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())

    plan = service.create_membership_plan("订单套餐", 8, 40, "用于测试订单")
    order = service.create_order(plan.id, 39.9, "待支付", "待确认")
    updated = service.update_order(
        order.id,
        {"plan_id": plan.id, "amount": 39.9, "status": "已支付", "note": "已完成收款"},
    )

    assert updated.status == "已支付"
    assert updated.note == "已完成收款"


def test_selecting_outline_regenerates_drafts() -> None:
    runner = FakeAgentRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]
    target_option = chapter.outline_options[0]

    updated = service.select_outline_option(project_id, chapter.id, target_option.id)
    selected_option = next(option for option in updated.outline_options if option.selected)
    selected_draft = next(draft for draft in updated.drafts if draft.selected)

    assert selected_option.id == target_option.id
    assert selected_draft.content.startswith("AI 正文 AI 方案 1")


def test_updating_draft_creates_new_selected_revision() -> None:
    runner = FakeAgentRunner()
    service = NovelService(InMemoryStore(), agent_runner=runner)
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    chapter = service.get_project(project_id).chapters[0]

    updated = service.update_chapter_draft(project_id, chapter.id, "人工修改后的章节正文")
    selected_draft = next(draft for draft in updated.drafts if draft.selected)

    assert selected_draft.content == "人工修改后的章节正文"
    assert selected_draft.revision_no == 3


def test_create_task_rejects_when_quota_is_zero() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    quota = service.db.get_user_quota("")
    quota.daily_remaining = 0
    quota.monthly_remaining = 0
    quota.bonus_remaining = 0

    try:
        service.create_task(
            project_id,
            TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
        )
    except DomainError as exc:
        assert exc.code == "QUOTA_EXCEEDED"
    else:
        raise AssertionError("expected QUOTA_EXCEEDED")


def test_run_task_fails_immediately_when_runtime_quota_is_exhausted() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    quota = service.db.get_user_quota("")
    quota.daily_remaining = 2
    quota.monthly_remaining = 0
    quota.bonus_remaining = 0
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=2, start_chapter_index=1),
    )
    quota.daily_remaining = 1
    quota.monthly_remaining = 0
    quota.bonus_remaining = 0

    try:
        service.run_task(project_id, task.id)
    except DomainError as exc:
        assert exc.code == "QUOTA_EXCEEDED"
    else:
        raise AssertionError("expected QUOTA_EXCEEDED")

    updated_task = next(item for item in service.get_project(project_id).tasks if item.id == task.id)


def test_daily_quota_resets_on_next_business_day() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    quota = service.db.get_user_quota("")
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(APP_BUSINESS_TIMEZONE)
    previous_local_day = (local_now - timedelta(days=1)).replace(hour=23, minute=50, second=0, microsecond=0)
    quota.daily_remaining = 0
    quota.last_daily_reset_at = previous_local_day.astimezone(timezone.utc)

    refreshed = service.db.refresh_quota_periods("")

    assert refreshed.daily_remaining == service.db.membership_plans[service.db.active_plan_id].daily_free_chapters


def test_new_user_quota_does_not_inherit_default_bonus_quota() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    service.db.user_quota.bonus_remaining = 5

    quota = service.db.get_user_quota("new-user-001")

    assert quota.bonus_remaining == 0


def test_delete_chapter_clears_chapter_memory_before_regeneration() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.auto, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    project = service.get_project(project_id)
    chapter = project.chapters[0]

    assert any(item.get("chapter_index") == 1 for item in project.memory.chapter_summaries)
    assert any(item.get("chapter_index") == 1 for item in project.memory.timeline_nodes)
    assert any(item.get("chapter_index") == 1 for item in project.memory.major_events)
    assert any(item.get("chapter_index") == 1 for item in project.memory.fact_records)

    service.delete_chapter("", project_id, chapter.id)
    cleared = service.get_project(project_id)
    related_task = next(item for item in cleared.tasks if item.id == task.id)

    assert not any(item.get("chapter_index") == 1 for item in cleared.memory.chapter_summaries)
    assert not any(item.get("chapter_index") == 1 for item in cleared.memory.timeline_nodes)
    assert not any(item.get("chapter_index") == 1 for item in cleared.memory.major_events)
    assert not any(item.get("chapter_index") == 1 for item in cleared.memory.fact_records)
    assert not any(item.get("introduced_chapter_index") == 1 for item in cleared.memory.foreshadow_threads)
    assert related_task.status.value == "completed"


def test_delete_chapter_fails_active_manual_task() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.manual, chapter_count=1, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    project = service.get_project(project_id)
    chapter = project.chapters[0]
    active_task = next(item for item in project.tasks if item.id == task.id)

    assert active_task.status.value == "waiting_user_confirm"

    service.delete_chapter("", project_id, chapter.id)
    cleared = service.get_project(project_id)
    updated_task = next(item for item in cleared.tasks if item.id == task.id)

    assert updated_task.status.value == "failed"


def test_manual_multichapter_confirm_advances_to_next_generated_chapter() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.manual, chapter_count=2, start_chapter_index=1),
    )

    first_result = service.run_task(project_id, task.id)
    first_project = service.get_project(project_id)
    first_chapter = first_project.chapters[0]

    assert first_result.status.value == "waiting_user_confirm"
    assert first_result.chapter_ids == [first_chapter.id]

    second_result = service.confirm_chapter("", project_id, first_chapter.id)
    refreshed = service.get_project(project_id)

    assert second_result.status.value == "waiting_user_confirm"
    assert len(refreshed.chapters) == 2
    assert refreshed.chapters[1].chapter_index == 2
    assert refreshed.chapters[1].id in second_result.chapter_ids
    assert second_result.current_chapter_index == 3


def test_get_project_reconciles_missing_task_chapter_ids_for_generated_manual_chapters() -> None:
    service = NovelService(InMemoryStore(), agent_runner=FakeAgentRunner())
    project_id = make_project(service)
    task = service.create_task(
        project_id,
        TaskCreateRequest(mode=TaskMode.manual, chapter_count=2, start_chapter_index=1),
    )
    service.run_task(project_id, task.id)
    first_project = service.get_project(project_id)
    first_chapter = first_project.chapters[0]
    service.confirm_chapter("", project_id, first_chapter.id)

    broken_project = service.db.projects[project_id]
    broken_task = next(item for item in broken_project.tasks if item.id == task.id)
    broken_task.chapter_ids = [first_chapter.id]
    service.db.save_project(broken_project)

    repaired = service.get_project(project_id)
    repaired_task = next(item for item in repaired.tasks if item.id == task.id)

    assert len(repaired_task.chapter_ids) == 2
    assert repaired.chapters[1].id in repaired_task.chapter_ids
