import json
import os
import subprocess

from apps.backend.agent_runner import AgentRunner
from apps.backend.models import Project, ProjectMemory, TaskMode
from apps.backend import agent_runner_openai


def test_agent_runner_reads_command_from_env_at_call_time(tmp_path, monkeypatch) -> None:
    script_path = tmp_path / "echo_runner.py"
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "payload = json.loads(sys.stdin.read())",
                "action = payload['action']",
                "if action == 'chapter_outlines':",
                "    result = {",
                "        'options': [",
                "            {'option_no': 1, 'content': '命令方案1', 'core_conflict': '冲突1', 'key_event': '事件1', 'ending_hook': '钩子1', 'score_plot': 8.1, 'score_consistency': 8.1, 'score_hook': 8.1, 'final_score': 8.1, 'editor_comment': '点评1'},",
                "            {'option_no': 2, 'content': '命令方案2', 'core_conflict': '冲突2', 'key_event': '事件2', 'ending_hook': '钩子2', 'score_plot': 8.2, 'score_consistency': 8.2, 'score_hook': 8.2, 'final_score': 8.2, 'editor_comment': '点评2'},",
                "            {'option_no': 3, 'content': '命令方案3', 'core_conflict': '冲突3', 'key_event': '事件3', 'ending_hook': '钩子3', 'score_plot': 8.3, 'score_consistency': 8.3, 'score_hook': 8.3, 'final_score': 8.3, 'editor_comment': '点评3'},",
                "        ]",
                "    }",
                "else:",
                "    result = {'text': '命令返回正文'}",
                "sys.stdout.write(json.dumps(result, ensure_ascii=False))",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("AGENT_RUNNER_COMMAND", raising=False)
    monkeypatch.delenv("AGENT_RUNNER_URL", raising=False)

    runner = AgentRunner()

    monkeypatch.setenv("AGENT_RUNNER_COMMAND", f"{os.sys.executable} {script_path}")
    payload = runner._invoke("chapter_draft", {"chapter_index": 1})

    assert payload == {"text": "命令返回正文"}
    assert runner._resolve_source() == "command"


def test_agent_runner_returns_fallback_when_command_times_out(monkeypatch) -> None:
    runner = AgentRunner()
    monkeypatch.setenv("AGENT_RUNNER_COMMAND", "python apps/backend/agent_runner_openai.py")
    monkeypatch.delenv("AGENT_RUNNER_URL", raising=False)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd=kwargs.get("args", args[0] if args else []), timeout=12)
        ),
    )
    monkeypatch.setattr(runner, "_command_timeout_seconds", lambda: 12)

    payload = runner._invoke("chapter_draft", {"chapter_index": 3})

    assert payload["_meta"]["fallback"] is True
    assert payload["_meta"]["action"] == "chapter_draft"
    assert payload["_meta"]["reason"] == "command_timeout"
    assert payload["_meta"]["timeout_seconds"] == 12


def test_build_request_contexts_uses_full_context_before_compact_retry() -> None:
    context = {
        "summary": "主角在旧都追查真相",
        "global_outline": "第一卷围绕身份反转展开",
        "world_rules": ["规则一", "规则二", "规则三"],
        "character_cards": ["主角", "盟友", "对手", "导师"],
    }

    contexts = agent_runner_openai.build_request_contexts("chapter_draft", context)

    assert len(contexts) == 2
    assert contexts[0] == context
    assert contexts[1]["_retry_mode"] == "compact"
    assert contexts[1]["summary"] == context["summary"][:120]
    assert contexts[1]["character_cards"] == context["character_cards"][:3]


def test_chapter_draft_prompt_targets_longer_output_and_consistency() -> None:
    prompt = agent_runner_openai.build_system_prompt("chapter_draft")
    config = agent_runner_openai.action_request_config("chapter_draft")

    assert "2800 到 3400 个中文字符" in prompt
    assert "主角人设" in prompt
    assert "2400 到 3000 个中文字符" in prompt
    assert "不要出现解释腔、提纲腔、总结腔、鸡汤金句腔" in prompt
    assert "如果输入里有 style_rules" in prompt
    assert "latest_scene_bridge" in prompt
    assert "严禁把上一章已经推进到高进度或后段的流程" in prompt
    assert config["max_tokens"] == 3600


def test_chapter_outline_prompt_mentions_hard_continuity_constraints() -> None:
    prompt = agent_runner_openai.build_system_prompt("chapter_outlines")

    assert "latest_scene_bridge" in prompt
    assert "必须直接承接上一章最后状态" in prompt
    assert "不得无解释回退到更早阶段" in prompt
    assert "不能把主线写成现代实验室悬疑" in prompt


def test_genre_style_brief_returns_targeted_guidance() -> None:
    assert "情绪变化压进互动细节" in agent_runner_openai.genre_style_brief("romance")
    assert "技术设定落实到行动限制" in agent_runner_openai.genre_style_brief("sci_fi")
    assert "具体场景" in agent_runner_openai.genre_style_brief("unknown_genre")


def test_genre_style_exemplars_returns_positive_examples() -> None:
    assert "动作迟疑" in agent_runner_openai.genre_style_exemplars("romance")
    assert "异象先落在触感" in agent_runner_openai.genre_style_exemplars("fantasy")
    assert "先写眼前发生的事" in agent_runner_openai.genre_style_exemplars("unknown_genre")


def test_call_chat_completions_includes_genre_exemplar_in_system_message(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json_bytes

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["request"] = request
        captured["timeout"] = timeout
        return DummyResponse()

    json_bytes = (
        '{"choices":[{"message":{"content":"{\\"text\\":\\"正文\\"}"}}]}'
    ).encode("utf-8")
    monkeypatch.setattr(agent_runner_openai.urllib.request, "urlopen", fake_urlopen)

    agent_runner_openai.call_chat_completions(
        base_url="http://example.test/v1",
        api_key="token",
        model="test-model",
        action="chapter_draft",
        context={"genre": "romance", "summary": "test"},
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    system_message = body["messages"][0]["content"]
    assert "当前题材正向示例：" in system_message
    assert "动作迟疑" in system_message


def test_genre_hard_constraints_are_included_in_system_message(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json_bytes

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["request"] = request
        captured["timeout"] = timeout
        return DummyResponse()

    json_bytes = (
        '{"choices":[{"message":{"content":"{\\"options\\":[{\\"option_no\\":1,\\"content\\":\\"方案1\\",\\"core_conflict\\":\\"冲突1\\",\\"key_event\\":\\"事件1\\",\\"ending_hook\\":\\"钩子1\\",\\"score_plot\\":8.1,\\"score_consistency\\":8.1,\\"score_hook\\":8.1,\\"final_score\\":8.1,\\"editor_comment\\":\\"点评1\\"},{\\"option_no\\":2,\\"content\\":\\"方案2\\",\\"core_conflict\\":\\"冲突2\\",\\"key_event\\":\\"事件2\\",\\"ending_hook\\":\\"钩子2\\",\\"score_plot\\":8.2,\\"score_consistency\\":8.2,\\"score_hook\\":8.2,\\"final_score\\":8.2,\\"editor_comment\\":\\"点评2\\"},{\\"option_no\\":3,\\"content\\":\\"方案3\\",\\"core_conflict\\":\\"冲突3\\",\\"key_event\\":\\"事件3\\",\\"ending_hook\\":\\"钩子3\\",\\"score_plot\\":8.3,\\"score_consistency\\":8.3,\\"score_hook\\":8.3,\\"final_score\\":8.3,\\"editor_comment\\":\\"点评3\\"}]}"}}]}'
    ).encode("utf-8")
    monkeypatch.setattr(agent_runner_openai.urllib.request, "urlopen", fake_urlopen)

    agent_runner_openai.call_chat_completions(
        base_url="http://example.test/v1",
        api_key="token",
        model="test-model",
        action="chapter_outlines",
        context={"genre": "fantasy", "summary": "test"},
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    system_message = body["messages"][0]["content"]
    assert "当前题材必须满足：" in system_message
    assert "当前题材禁止串台：" in system_message
    assert "现代悬疑" in system_message


def test_generate_outline_options_with_context_passes_user_idea(monkeypatch) -> None:
    runner = AgentRunner()
    captured: dict[str, object] = {}

    def fake_invoke(action: str, payload: dict[str, object]) -> dict[str, object]:
      captured["action"] = action
      captured["payload"] = payload
      return {
          "options": [
              {"option_no": 1, "content": "方案1", "core_conflict": "冲突1", "key_event": "事件1", "ending_hook": "钩子1", "score_plot": 8.1, "score_consistency": 8.2, "score_hook": 8.3, "final_score": 8.2, "editor_comment": "点评1"},
              {"option_no": 2, "content": "方案2", "core_conflict": "冲突2", "key_event": "事件2", "ending_hook": "钩子2", "score_plot": 8.2, "score_consistency": 8.3, "score_hook": 8.4, "final_score": 8.3, "editor_comment": "点评2"},
              {"option_no": 3, "content": "方案3", "core_conflict": "冲突3", "key_event": "事件3", "ending_hook": "钩子3", "score_plot": 8.3, "score_consistency": 8.4, "score_hook": 8.5, "final_score": 8.4, "editor_comment": "点评3"},
          ]
      }

    monkeypatch.setattr(runner, "_invoke", fake_invoke)
    project = Project(
        id="project-1",
        title="测试项目",
        genre="fantasy",
        summary="主角卷入旧王都谜案",
        length_type="long",
        template_id="tpl-1",
        mode_default=TaskMode.manual,
        memory=ProjectMemory(
            global_outline="",
            character_cards=[],
            character_profiles=[],
            relationship_states=[],
            world_rules=[],
            event_summary=[],
            chapter_summaries=[],
            foreshadow_threads=[],
            timeline_nodes=[],
            major_events=[],
            fact_records=[],
        ),
    )

    runner.generate_outline_options_with_context(
        project,
        1,
        {
            "user_idea": "希望增加一次公开对峙，并让误会继续升级",
            "story_beats": [{"phase_index": 1, "label": "起势阶段"}],
            "active_phase": {"phase_index": 1, "phase_goal": "让冲突开始失衡"},
            "retrieval_focus": {"query_text": "test"},
        },
    )

    assert captured["action"] == "chapter_outlines"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["user_idea"] == "希望增加一次公开对峙，并让误会继续升级"
    assert payload["story_beats"] == [{"phase_index": 1, "label": "起势阶段"}]
    assert payload["active_phase"] == {"phase_index": 1, "phase_goal": "让冲突开始失衡"}


def test_memory_context_passes_template_guidance() -> None:
    runner = AgentRunner()
    project = Project(
        id="project-1",
        title="测试项目",
        genre="fantasy",
        summary="主角卷入旧王都谜案",
        length_type="long",
        template_id="tpl-1",
        mode_default=TaskMode.manual,
        memory=ProjectMemory(
            global_outline="",
            character_cards=[],
            character_profiles=[],
            relationship_states=[],
            world_rules=[],
            event_summary=[],
            chapter_summaries=[],
            foreshadow_threads=[],
            timeline_nodes=[],
            major_events=[],
            fact_records=[],
        ),
    )

    context = runner._memory_context(
        project,
        {
            "style_rules": "冷硬克制，少抒情总结",
            "world_template": "雨夜旧城",
            "character_template": "调查者与线人",
            "outline_template": "发现、试探、反转",
        },
    )

    assert context["style_rules"] == "冷硬克制，少抒情总结"
    assert context["world_template"] == "雨夜旧城"
    assert context["character_template"] == "调查者与线人"
    assert context["outline_template"] == "发现、试探、反转"
