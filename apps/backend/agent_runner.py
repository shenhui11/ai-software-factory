from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from apps.backend.models import Chapter, ChapterTransformRequest, OutlineOption, Project


@dataclass(slots=True)
class AgentTextResult:
    text: str
    source: str
    fallback: bool = False


@dataclass(slots=True)
class AgentOutlineResult:
    options: list[dict[str, object]]
    source: str
    fallback: bool = False


@dataclass(slots=True)
class AgentReviewResult:
    score_readability: float
    score_tension: float
    score_consistency: float
    final_score: float
    issue_summary: str
    source: str
    fallback: bool = False


class AgentRunner:
    def __init__(self) -> None:
        pass

    def generate_project_foundation(self, payload: dict[str, object]) -> dict[str, object]:
        response = self._invoke("project_foundation", payload)
        required_keys = {"summary", "character_cards", "world_rules", "event_summary"}
        if required_keys.issubset(response.keys()):
            return {
                "summary": str(response["summary"]).strip(),
                "character_cards": [str(item).strip() for item in response["character_cards"] if str(item).strip()],
                "world_rules": [str(item).strip() for item in response["world_rules"] if str(item).strip()],
                "event_summary": [str(item).strip() for item in response["event_summary"] if str(item).strip()],
                "source": self._resolve_source(),
                "fallback": self._is_fallback(response),
            }
        return self._local_project_foundation(payload)

    def expand_chapter(
        self,
        project: Project,
        chapter: Chapter,
        payload: ChapterTransformRequest,
    ) -> AgentTextResult:
        response = self._invoke(
            "chapter_expand",
            {
                "project_title": project.title,
                "genre": project.genre,
                "summary": project.summary,
                "latest_event": project.memory.event_summary[-1] if project.memory.event_summary else "",
                "world_rules": project.memory.world_rules,
                "character_cards": project.memory.character_cards,
                "character_profiles": project.memory.character_profiles,
                "relationship_states": project.memory.relationship_states,
                "chapter_summaries": project.memory.chapter_summaries[-5:],
                "chapter_title": chapter.title,
                "instruction": payload.instruction,
                "chapter_content": payload.chapter_content or "",
            },
        )
        text = self._extract_text(response)
        if text is not None:
            return AgentTextResult(
                text=text,
                source=self._resolve_source(),
                fallback=self._is_fallback(response),
            )
        return AgentTextResult(
            text=self._local_expand(project, chapter, payload),
            source="local",
            fallback=True,
        )

    def rewrite_chapter(
        self,
        project: Project,
        chapter: Chapter,
        payload: ChapterTransformRequest,
    ) -> AgentTextResult:
        response = self._invoke(
            "chapter_rewrite",
            {
                "project_title": project.title,
                "genre": project.genre,
                "summary": project.summary,
                "latest_event": project.memory.event_summary[-1] if project.memory.event_summary else "",
                "world_rules": project.memory.world_rules,
                "character_cards": project.memory.character_cards,
                "character_profiles": project.memory.character_profiles,
                "relationship_states": project.memory.relationship_states,
                "chapter_summaries": project.memory.chapter_summaries[-5:],
                "chapter_title": chapter.title,
                "instruction": payload.instruction,
                "chapter_content": payload.chapter_content or "",
            },
        )
        text = self._extract_text(response)
        if text is not None:
            return AgentTextResult(
                text=text,
                source=self._resolve_source(),
                fallback=self._is_fallback(response),
            )
        return AgentTextResult(
            text=self._local_rewrite(project, chapter, payload),
            source="local",
            fallback=True,
        )

    def generate_outline_options(self, project: Project, chapter_index: int) -> AgentOutlineResult:
        return self.generate_outline_options_with_context(project, chapter_index, None)

    def generate_outline_options_with_context(
        self,
        project: Project,
        chapter_index: int,
        context_packet: dict[str, object] | None,
    ) -> AgentOutlineResult:
        memory_context = self._memory_context(project, context_packet)
        response = self._invoke(
            "chapter_outlines",
            {
                "project_title": project.title,
                "genre": project.genre,
                "summary": project.summary,
                "chapter_index": chapter_index,
                **memory_context,
            },
        )
        options = response.get("options")
        if isinstance(options, list) and len(options) == 3:
            return AgentOutlineResult(
                options=options,
                source=self._resolve_source(),
                fallback=self._is_fallback(response),
            )
        return AgentOutlineResult(
            options=self._local_outline_options(project, chapter_index),
            source="local",
            fallback=True,
        )

    def generate_draft(
        self,
        project: Project,
        chapter: Chapter,
        option: OutlineOption,
        revision_no: int,
        previous_issues: list[str],
    ) -> AgentTextResult:
        return self.generate_draft_with_context(project, chapter, option, revision_no, previous_issues, None)

    def generate_draft_with_context(
        self,
        project: Project,
        chapter: Chapter,
        option: OutlineOption,
        revision_no: int,
        previous_issues: list[str],
        context_packet: dict[str, object] | None,
    ) -> AgentTextResult:
        memory_context = self._memory_context(project, context_packet)
        response = self._invoke(
            "chapter_draft",
            {
                "project_title": project.title,
                "genre": project.genre,
                "summary": project.summary,
                "chapter_index": chapter.chapter_index,
                "chapter_title": chapter.title,
                "selected_option": option.model_dump(mode="json"),
                **memory_context,
                "revision_no": revision_no,
                "previous_issues": previous_issues,
            },
        )
        text = self._extract_text(response)
        if text is not None:
            return AgentTextResult(
                text=text,
                source=self._resolve_source(),
                fallback=self._is_fallback(response),
            )
        return AgentTextResult(
            text=self._local_draft(project, chapter, option, revision_no, previous_issues),
            source="local",
            fallback=True,
        )

    def review_draft(
        self,
        project: Project,
        chapter: Chapter,
        option: OutlineOption,
        draft_content: str,
        revision_no: int,
    ) -> AgentReviewResult:
        return self.review_draft_with_context(project, chapter, option, draft_content, revision_no, None)

    def review_draft_with_context(
        self,
        project: Project,
        chapter: Chapter,
        option: OutlineOption,
        draft_content: str,
        revision_no: int,
        context_packet: dict[str, object] | None,
    ) -> AgentReviewResult:
        memory_context = self._memory_context(project, context_packet)
        response = self._invoke(
            "chapter_review",
            {
                "project_title": project.title,
                "genre": project.genre,
                "summary": project.summary,
                "chapter_index": chapter.chapter_index,
                "chapter_title": chapter.title,
                "selected_option": option.model_dump(mode="json"),
                "draft_content": draft_content,
                "revision_no": revision_no,
                **memory_context,
            },
        )
        review = self._extract_review(response)
        if review is not None:
            return AgentReviewResult(
                source=self._resolve_source(),
                fallback=self._is_fallback(response),
                **review,
            )
        return AgentReviewResult(
            source="local",
            fallback=True,
            **self._local_review(project, chapter, draft_content, revision_no),
        )

    def _memory_context(self, project: Project, context_packet: dict[str, object] | None) -> dict[str, object]:
        if context_packet:
            return {
                "latest_event": context_packet.get("recent_events", [""])[-1] if context_packet.get("recent_events") else "",
                "global_outline": context_packet.get("global_outline", project.memory.global_outline),
                "world_rules": context_packet.get("world_rules", project.memory.world_rules),
                "character_cards": context_packet.get("character_cards", project.memory.character_cards),
                "character_profiles": context_packet.get("character_profiles", project.memory.character_profiles),
                "relationship_states": context_packet.get("relationship_states", project.memory.relationship_states),
                "story_beats": context_packet.get("story_beats", project.memory.story_beats[-3:]),
                "active_phase": context_packet.get("active_phase", project.memory.active_phase),
                "chapter_summaries": context_packet.get("chapter_summaries", project.memory.chapter_summaries[-5:]),
                "timeline_nodes": context_packet.get("timeline_nodes", project.memory.timeline_nodes[-5:]),
                "major_events": context_packet.get("major_events", project.memory.major_events[-5:]),
                "fact_records": context_packet.get("fact_records", project.memory.fact_records[-8:]),
                "active_foreshadows": context_packet.get("active_foreshadows", project.memory.foreshadow_threads[-5:]),
                "retrieval_focus": context_packet.get("retrieval_focus", {}),
                "consistency_rules": context_packet.get("consistency_rules", []),
                "user_idea": context_packet.get("user_idea", ""),
                "style_rules": context_packet.get("style_rules", ""),
                "world_template": context_packet.get("world_template", ""),
                "character_template": context_packet.get("character_template", ""),
                "outline_template": context_packet.get("outline_template", ""),
            }
        return {
            "latest_event": project.memory.event_summary[-1] if project.memory.event_summary else "",
            "global_outline": project.memory.global_outline,
            "world_rules": project.memory.world_rules,
            "character_cards": project.memory.character_cards,
            "character_profiles": project.memory.character_profiles,
            "relationship_states": project.memory.relationship_states,
            "story_beats": project.memory.story_beats[-3:],
            "active_phase": project.memory.active_phase,
            "chapter_summaries": project.memory.chapter_summaries[-5:],
            "timeline_nodes": project.memory.timeline_nodes[-5:],
            "major_events": project.memory.major_events[-5:],
            "fact_records": project.memory.fact_records[-8:],
            "active_foreshadows": project.memory.foreshadow_threads[-5:],
            "retrieval_focus": {},
            "consistency_rules": [],
            "user_idea": "",
            "style_rules": "",
            "world_template": "",
            "character_template": "",
            "outline_template": "",
        }

    def _call_command(self, prompt: str, command: str) -> dict[str, object]:
        timeout_seconds = self._command_timeout_seconds()
        started_at = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603,S607
                shlex.split(command),
                input=prompt.encode("utf-8"),
                capture_output=True,
                check=True,
                timeout=timeout_seconds,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            if stderr:
                print(stderr, file=sys.stderr)
            raise RuntimeError(f"Agent runner command failed: {stderr or exc}") from exc
        except subprocess.TimeoutExpired as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            if stderr:
                print(stderr, file=sys.stderr)
            raise
        elapsed = round(time.monotonic() - started_at, 3)
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        if stderr:
            print(stderr, file=sys.stderr)
        print(
            (
                f"[agent_runner] command_success elapsed_seconds={elapsed if elapsed is not None else 'unknown'} "
                f"command={command} "
                f"stdout_chars={len(completed.stdout)} stderr_chars={len(completed.stderr)}"
            ),
            file=sys.stderr,
        )
        return self._parse_output(completed.stdout.decode("utf-8"))

    def _call_http(self, prompt: str, url: str) -> dict[str, object]:
        timeout_seconds = self._command_timeout_seconds()
        request = urllib.request.Request(
            url,
            data=prompt.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.URLError as exc:  # pragma: no cover - network dependent
            raise RuntimeError("Agent runner request failed") from exc
        return self._parse_output(payload)

    def _invoke(self, action: str, context: dict[str, object]) -> dict[str, object]:
        prompt = json.dumps({"action": action, "context": context}, ensure_ascii=False)
        command = self._command()
        url = self._url()
        prompt_bytes = len(prompt.encode("utf-8"))
        print(
            (
                f"[agent_runner] invoke action={action} "
                f"has_command={bool(command)} has_url={bool(url)} "
                f"command={command or '<empty>'} url={url or '<empty>'} "
                f"prompt_bytes={prompt_bytes}"
            ),
            file=sys.stderr,
        )
        if command:
            try:
                payload = self._call_command(prompt, command)
                print(
                    f"[agent_runner] completed action={action} source=command fallback={self._is_fallback(payload)}",
                    file=sys.stderr,
                )
                return payload
            except subprocess.TimeoutExpired:
                timeout_seconds = self._command_timeout_seconds()
                print(
                    (
                        f"[agent_runner] command timeout action={action} "
                        f"timeout_seconds={timeout_seconds} command={command} prompt_bytes={prompt_bytes}"
                    ),
                    file=sys.stderr,
                )
                return {
                    "_meta": {
                        "fallback": True,
                        "action": action,
                        "reason": "command_timeout",
                        "timeout_seconds": timeout_seconds,
                        "prompt_bytes": prompt_bytes,
                    }
                }
        if url:
            payload = self._call_http(prompt, url)
            print(
                f"[agent_runner] completed action={action} source=http fallback={self._is_fallback(payload)}",
                file=sys.stderr,
            )
            return payload
        print(f"[agent_runner] completed action={action} source=local-empty fallback=True", file=sys.stderr)
        return {}

    def _parse_output(self, raw_output: str) -> dict[str, object]:
        payload = json.loads(raw_output)
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("Agent runner returned invalid output")

    def _extract_text(self, payload: dict[str, object]) -> str | None:
        text = payload.get("text") or payload.get("updated") or payload.get("content")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return None

    def _extract_review(self, payload: dict[str, object]) -> dict[str, float | str] | None:
        issue_summary = payload.get("issue_summary")
        numeric_values = {
            "score_readability": payload.get("score_readability"),
            "score_tension": payload.get("score_tension"),
            "score_consistency": payload.get("score_consistency"),
            "final_score": payload.get("final_score"),
        }
        if not isinstance(issue_summary, str) or not issue_summary.strip():
            return None
        if not all(isinstance(value, (int, float)) for value in numeric_values.values()):
            return None
        return {
            "score_readability": float(numeric_values["score_readability"]),
            "score_tension": float(numeric_values["score_tension"]),
            "score_consistency": float(numeric_values["score_consistency"]),
            "final_score": float(numeric_values["final_score"]),
            "issue_summary": issue_summary.strip(),
        }

    def _is_fallback(self, payload: dict[str, object]) -> bool:
        meta = payload.get("_meta")
        if isinstance(meta, dict):
            return bool(meta.get("fallback"))
        return False

    def _resolve_source(self) -> str:
        if self._command():
            return "command"
        if self._url():
            return "http"
        return "local"

    def _command(self) -> str:
        configured = os.getenv("AGENT_RUNNER_COMMAND", "").strip()
        if configured:
            return configured
        if os.getenv("AGENT_RUNNER_URL", "").strip():
            return ""
        return f"{sys.executable} apps/backend/agent_runner_openai.py"

    def _url(self) -> str:
        return os.getenv("AGENT_RUNNER_URL", "").strip()

    def _command_timeout_seconds(self) -> int:
        raw_value = os.getenv("AGENT_RUNNER_TIMEOUT_SECONDS", "").strip()
        if raw_value.isdigit():
            return max(10, int(raw_value))
        return 300

    def _local_outline_options(self, project: Project, chapter_index: int) -> list[dict[str, object]]:
        base = [
            ("一条被掩埋的线索改写了现有阵营关系", 8.2, 8.0, 8.4),
            ("一次公开对峙抬高了人物情绪与风险", 8.8, 8.4, 8.7),
            ("一段安静支线补强设定，但会拖慢节奏", 7.8, 8.6, 7.5),
        ]
        options: list[dict[str, object]] = []
        for index, (theme, plot, consistency, hook) in enumerate(base, start=1):
            options.append(
                {
                    "option_no": index,
                    "content": f"第 {chapter_index} 章方案 {index}：{theme}。",
                    "core_conflict": f"{project.title} 在本章面临的核心冲突 {index}",
                    "key_event": f"第 {chapter_index} 章关键事件 {index}",
                    "ending_hook": f"第 {chapter_index} 章结尾钩子 {index}",
                    "score_plot": plot,
                    "score_consistency": consistency,
                    "score_hook": hook,
                    "final_score": round((plot + consistency + hook) / 3, 2),
                    "editor_comment": f"方案 {index} 在连贯性与推进节奏之间更均衡。",
                }
            )
        return options

    def _local_draft(
        self,
        project: Project,
        chapter: Chapter,
        option: OutlineOption,
        revision_no: int,
        previous_issues: list[str],
    ) -> str:
        issue_line = f"针对上一轮问题：{'；'.join(previous_issues)}" if previous_issues else "首轮起稿。"
        return (
            f"《{project.title}》第 {chapter.chapter_index} 章修订稿 {revision_no}。\n"
            f"基于已选剧情方案生成：{option.content}\n"
            f"{issue_line}"
        )

    def _local_review(
        self,
        project: Project,
        chapter: Chapter,
        draft_content: str,
        revision_no: int,
    ) -> dict[str, float | str]:
        if project.genre == "horror":
            scores = [7.4, 7.6, 7.7, 7.8, 7.85, 7.9]
            score = scores[min(revision_no - 1, len(scores) - 1)]
        else:
            score = 7.6 if revision_no == 1 else 8.4
        return {
            "score_readability": round(score - 0.1, 2),
            "score_tension": round(score, 2),
            "score_consistency": round(min(score + 0.1, 8.9), 2),
            "final_score": score,
            "issue_summary": (
                "情绪爆点仍然偏弱，需要进一步强化。"
                if score < 8.0
                else "已达到当前发布阈值。"
            ),
        }

    def _local_project_foundation(self, payload: dict[str, object]) -> dict[str, object]:
        title = str(payload.get("title") or "未命名项目").strip()
        genre = str(payload.get("genre") or "fantasy").strip()
        summary = str(payload.get("summary") or "").strip()
        character_cards = [str(item).strip() for item in payload.get("character_cards", []) if str(item).strip()]
        world_rules = [str(item).strip() for item in payload.get("world_rules", []) if str(item).strip()]
        event_summary = [str(item).strip() for item in payload.get("event_summary", []) if str(item).strip()]

        genre_defaults = {
            "fantasy": {
                "summary": f"{title}围绕失落秩序、代价魔法与权力裂变展开，主角必须在真相与牺牲之间作出选择。",
                "characters": ["背负秘密的主角", "立场复杂的盟友", "潜伏多年的对手"],
                "world_rules": ["力量使用伴随明确代价", "古老秩序仍在暗中影响现实"],
                "events": ["旧时代灾变留下未解后果", "主角意外接触改变命运的线索"],
            },
            "romance": {
                "summary": f"{title}聚焦高压处境下的情感拉扯与关系重建，人物在误解、选择与代价中推进故事。",
                "characters": ["外冷内热的主角", "难以看穿真实意图的对象", "推动关系变化的第三方角色"],
                "world_rules": ["情感选择会直接改变现实关系网络", "公开承诺会带来额外代价"],
                "events": ["一次意外相遇打破既有生活节奏", "过往关系的旧伤被重新揭开"],
            },
            "horror": {
                "summary": f"{title}以逐步逼近的未知威胁推进剧情，角色在恐惧、怀疑与求生中揭开真相。",
                "characters": ["对异常最先产生警觉的主角", "掌握片段真相却不愿直说的见证者", "可能被污染或利用的同伴"],
                "world_rules": ["异常现象不会无代价出现", "知晓越多的人越容易被盯上"],
                "events": ["一次异常事件打破日常秩序", "角色发现过去记录与当前灾异存在呼应"],
            },
        }
        defaults = genre_defaults.get(genre, {
            "summary": f"{title}围绕角色目标、外部冲突与持续升级的选择代价展开。",
            "characters": ["核心主角", "关键盟友", "主要对立角色"],
            "world_rules": ["世界运转存在清晰限制", "关键选择会持续改变后续局势"],
            "events": ["故事从一次异常变化或目标触发开始", "角色很快被卷入更大的冲突"],
        })

        return {
            "summary": summary or defaults["summary"],
            "character_cards": character_cards or defaults["characters"],
            "world_rules": world_rules or defaults["world_rules"],
            "event_summary": event_summary or defaults["events"],
            "source": "local",
            "fallback": True,
        }

    def _local_rewrite(self, project: Project, chapter: Chapter, payload: ChapterTransformRequest) -> str:
        details: list[str] = [payload.chapter_content or f"{chapter.title} 的原正文", f"[整章重写建议] {payload.instruction}"]
        if project.memory.event_summary:
            details.append(f"[章节衔接] {project.memory.event_summary[-1]}")
        if chapter.selected_option_id:
            details.append("[写作目标] 保留当前章节已选剧情方案的推进方向。")
        return "\n".join(details)

    def _local_expand(self, project: Project, chapter: Chapter, payload: ChapterTransformRequest) -> str:
        details: list[str] = [payload.chapter_content or f"{chapter.title} 的原正文", f"[整章扩写补充] {payload.instruction}"]
        if project.memory.event_summary:
            details.append(f"[章节衔接] {project.memory.event_summary[-1]}")
        if project.memory.character_cards:
            details.append(f"[人物推进] {project.memory.character_cards[0]}的情绪与反应被补充得更完整。")
        if chapter.selected_option_id:
            details.append("[走向延展] 本段继续沿着已选定的剧情方案推进。")
        return "\n".join(details)
