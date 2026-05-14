from __future__ import annotations

import json
import os
import time
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_MODEL = os.getenv("CODEX_MODEL", "gpt-5.4")
DEFAULT_BASE_URL = os.getenv("CODEX_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
DEFAULT_API_KEY = os.getenv("CODEX_API_KEY", "").strip()
DEBUG_ENABLED = os.getenv("AGENT_RUNNER_DEBUG", "").strip() == "1"
DRAFT_TARGET_MIN_CHARS = 2800
DRAFT_TARGET_MAX_CHARS = 3400
DRAFT_COMPACT_MIN_CHARS = 2400
DRAFT_COMPACT_MAX_CHARS = 3000


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        value = default
    else:
        try:
            value = int(raw_value)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


UPSTREAM_TIMEOUT_SECONDS = _env_int("CODEX_TIMEOUT_SECONDS", 240, minimum=30)
MAX_RETRIES = _env_int("CODEX_RETRY_ATTEMPTS", 2, minimum=0)


def action_request_config(action: str) -> dict[str, Any]:
    if action == "chapter_draft":
        return {"temperature": 0.4, "max_tokens": 3600}
    if action == "chapter_review":
        return {"temperature": 0.2, "max_tokens": 900}
    if action in {"chapter_rewrite", "chapter_expand"}:
        return {"temperature": 0.5, "max_tokens": 1800}
    if action == "chapter_outlines":
        return {"temperature": 0.4, "max_tokens": 2400}
    if action == "project_foundation":
        return {"temperature": 0.4, "max_tokens": 1200}
    return {"temperature": 0.6, "max_tokens": 1200}


def build_request_contexts(action: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    if action != "chapter_draft":
        return [context]
    return [context, shrink_context_for_retry(action, context)]


def shrink_context_for_retry(action: str, context: dict[str, Any]) -> dict[str, Any]:
    if action != "chapter_draft":
        return context
    reduced = dict(context)
    reduced["summary"] = str(context.get("summary", ""))[:120]
    reduced["global_outline"] = str(context.get("global_outline", ""))[:80]
    reduced["world_rules"] = [str(item)[:40] for item in list(context.get("world_rules", []))[:2]]
    reduced["character_cards"] = [str(item)[:20] for item in list(context.get("character_cards", []))[:3]]
    reduced["character_profiles"] = []
    reduced["relationship_states"] = []
    reduced["recent_events"] = [str(item)[:80] for item in list(context.get("recent_events", []))[-1:]]
    reduced["chapter_summaries"] = [str(item)[:80] for item in list(context.get("chapter_summaries", []))[-1:]]
    reduced["timeline_nodes"] = []
    reduced["major_events"] = [str(item)[:80] for item in list(context.get("major_events", []))[-1:]]
    reduced["fact_records"] = [str(item)[:80] for item in list(context.get("fact_records", []))[:2]]
    reduced["active_foreshadows"] = [str(item)[:60] for item in list(context.get("active_foreshadows", []))[:1]]
    reduced["consistency_rules"] = [str(item)[:50] for item in list(context.get("consistency_rules", []))[:3]]
    retrieval_focus = context.get("retrieval_focus", {})
    if isinstance(retrieval_focus, dict):
        reduced["retrieval_focus"] = {
            "query_text": str(retrieval_focus.get("query_text", ""))[:80],
            "characters": [str(item)[:20] for item in list(retrieval_focus.get("characters", []))[:2]],
            "terms": [str(item)[:30] for item in list(retrieval_focus.get("terms", []))[:4]],
        }
    selected_option = context.get("selected_option")
    if isinstance(selected_option, dict):
        reduced["selected_option"] = {
            "option_no": selected_option.get("option_no"),
            "content": str(selected_option.get("content", ""))[:180],
            "core_conflict": str(selected_option.get("core_conflict", ""))[:80],
            "key_event": str(selected_option.get("key_event", ""))[:80],
            "ending_hook": str(selected_option.get("ending_hook", ""))[:60],
        }
    reduced["previous_issues"] = [str(item)[:80] for item in list(context.get("previous_issues", []))[-1:]]
    reduced["_retry_mode"] = "compact"
    return reduced


def summarize_context_sizes(context: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(context, ensure_ascii=False)
    field_sizes: list[tuple[str, int]] = []
    for key, value in context.items():
        try:
            field_sizes.append((key, len(json.dumps(value, ensure_ascii=False))))
        except TypeError:
            field_sizes.append((key, len(str(value))))
    field_sizes.sort(key=lambda item: item[1], reverse=True)
    return {
        "context_chars": len(serialized),
        "context_bytes": len(serialized.encode("utf-8")),
        "largest_fields": field_sizes[:8],
    }


def build_system_prompt(action: str) -> str:
    common = (
        "你是中文小说生成与审稿助手。"
        "必须严格只输出 JSON，不要输出 markdown，不要输出解释。"
        "所有文案都必须是中文。"
    )
    anti_ai_style = (
        "语言必须像成熟网文作者的成稿，不要出现解释腔、提纲腔、总结腔、鸡汤金句腔。"
        "不要频繁使用“与此同时、然而、总之、某种意义上、仿佛预示着”这类万能连接句。"
        "不要刻意写工整排比、四字短句连发、观点先行的抒情总结。"
        "优先写具体动作、具体感官、具体反应，让情绪落在场景里，不要替读者概括主题。"
    )
    prompts = {
        "chapter_outlines": (
            f"{common}"
            f"{anti_ai_style}"
            "请返回 3 个章节走向方案。"
            "输出格式必须是 "
            '{"options":[{"option_no":1,"content":"","core_conflict":"","key_event":"","ending_hook":"","score_plot":8.1,"score_consistency":8.0,"score_hook":8.2,"final_score":8.1,"editor_comment":""}]}'
            "。必须正好 3 个方案，option_no 分别为 1、2、3。"
            "如果输入包含 style_rules、world_template、character_template、outline_template，必须把它们当作强约束，体现在方案气质、冲突密度、角色互动和推进方式里。"
            "如果输入包含 latest_scene_bridge、chapter_summaries、hard_constraints、continuity_state，这些都属于上一章结尾的硬承接信息。"
            "必须直接承接上一章最后状态，不得把已经推进到中后段的场景重写成刚开始发生。"
            "如果上一章存在明确进度值、强制流程、失能状态、封闭状态，不得无解释回退到更早阶段。"
            "必须严格服从题材，不得串台；如果项目题材是玄幻/奇幻/仙侠/武侠，就不能把主线写成现代实验室悬疑、病历调查、数据库追查、控制台解谜或机械回收流程。"
            "editor_comment 要像编辑批注，指出优缺点，不要写空泛夸奖。"
        ),
        "chapter_draft": (
            f"{common}"
            f"{anti_ai_style}"
            '请基于输入上下文生成章节正文。输出格式必须是 {"text":"..."}。'
            "正文必须自然成章，不能写成说明文，不能暴露提示词。"
            f"正文长度控制在约 {DRAFT_TARGET_MIN_CHARS} 到 {DRAFT_TARGET_MAX_CHARS} 个中文字符。"
            "优先保证主角人设、行为逻辑、情绪延续和与他人的关系状态前后一致。"
            "必须尊重人物性格锚点、关系状态和近期情节，不得让角色无缘无故变性。"
            "如果输入里有 style_rules，必须优先服从该文风规则；如果有 world_template、character_template、outline_template，要把它们落实到场景质感、人物说话方式和章节推进里。"
            "如果输入包含 latest_scene_bridge、chapter_summaries 里的 last_scene_excerpt/last_scene_summary、hard_constraints、continuity_state，必须把它们视为不可忽略的跨章硬约束。"
            "严禁把上一章已经推进到高进度或后段的流程，改写成从0%或刚开始重新发生。"
            "严禁把上一章已经失去行动能力或被强制牵引的角色，直接写回自由行动且不解释恢复过程。"
            "必须严格服从项目题材；如果题材是玄幻/奇幻/仙侠/武侠，主导冲突必须由超常法则、异象、修行代价、江湖秩序或非现实力量推动，不能滑向现代悬疑/硬科幻/实验室惊悚。"
            "不要在段首或段尾反复总结人物心境，不要用作者旁白替角色下结论。"
            "对话、动作、环境描写比例要自然波动，避免每段都用同样句式起承转合。"
            f"如果上下文里出现 _retry_mode=compact，请仍然尽量写到约 {DRAFT_COMPACT_MIN_CHARS} 到 {DRAFT_COMPACT_MAX_CHARS} 个中文字符，"
            "并优先保证关键事件和主角一致性，不要因为求短而跳过必要场景铺垫。"
        ),
        "chapter_review": (
            f"{common}"
            "请以资深读者视角评审正文。"
            '输出格式必须是 {"score_readability":8.2,"score_tension":8.3,"score_consistency":8.1,"final_score":8.2,"issue_summary":"..."}。'
            "分数范围 0 到 10，final_score 需要与评语一致。"
            "必须重点审查人物性格是否漂移、关系是否断裂、事件顺序是否冲突。"
            "必须审查题材是否跑偏；如果项目题材与正文主导推进类型不符，必须在 issue_summary 里直接指出题材串台或类型漂移。"
            "如果正文有明显解释腔、总结腔、排比过整或空泛抒情，要在 issue_summary 中直接指出。"
        ),
        "chapter_rewrite": (
            f"{common}"
            f"{anti_ai_style}"
            '请基于现有章节正文执行整章重写。输出格式必须是 {"text":"..."}。'
            "必须保留章节核心事件、人物关系与上下文一致性。"
            "如果输入中存在 style_rules、world_template、character_template、outline_template，重写时必须显式对齐这些约束。"
        ),
        "chapter_expand": (
            f"{common}"
            f"{anti_ai_style}"
            '请基于现有章节正文执行整章拓写。输出格式必须是 {"text":"..."}。'
            "新增内容必须自然衔接原文，并补足细节、氛围与人物推进。"
            "补写时只增加必要场景，不要为了拉长篇幅加入抽象总结或重复抒情。"
        ),
        "project_foundation": (
            f"{common}"
            '请基于项目名称、题材、模板与客户已填写字段，对项目基础设定做整体优化。输出格式必须是 {"summary":"","character_cards":[""],"world_rules":[""],"event_summary":[""],"story_beats":[{"phase_index":1,"label":"","phase_goal":"","phase_pressure":[""],"required_change":[""],"forbidden_outcomes":[""],"foreshadow_to_surface":[""],"tone_trend":"","flex_points":[""],"target_chapter_start":1,"target_chapter_end":3}]}。'
            "无论字段是否已有内容，都要在忠于客户输入的前提下整理、润色、补全，使其可以直接回填到表单。"
            "不得偏离客户已给出的核心设定，不要凭空改写主线方向。"
            "story_beats 只允许写阶段目标、压力、变化方向和约束，不允许写成逐章脚本。"
        ),
    }
    return prompts[action]


def genre_style_brief(genre: str) -> str:
    mapping = {
        "romance": "言情要把情绪变化压进互动细节、停顿、误读和关系拉扯里，避免空泛抒情和模板化心动描写。",
        "fantasy": "玄幻/奇幻要把力量规则、环境异质感和代价写进场景，不要只用抽象设定词堆气氛。",
        "horror": "恐怖要靠异常细节、感知偏差和递进压迫制造不安，不要直接解释恐惧。",
        "wuxia": "武侠要重招式选择、江湖分寸和人物气节，避免泛泛热血口号。",
        "xianxia": "仙侠要写出境界、因果、资源代价和师承关系，不要只堆术语。",
        "sci_fi": "科幻要让技术设定落实到行动限制、认知冲突和现实后果，不要把设定写成说明书。",
        "suspense": "悬疑要优先控制信息释放节奏和证据链，不要过早替读者总结方向。",
        "mystery": "推理要让线索、判断和反转有因果闭环，避免角色突然得出正确答案。",
        "thriller": "惊悚要靠即时风险、追逼感和决策压力推进，不要靠空喊危险。",
        "historical": "历史要注意身份秩序、时代措辞和现实约束，不要写成现代人套古装。",
        "urban": "都市要让语言更口语、更具体，少用高概念抒情。",
        "cyberpunk": "赛博朋克要突出技术异化、身体改造与秩序压迫，避免表面霓虹化。",
        "slice_of_life": "日常要靠生活纹理和关系细节立住，不要硬造大冲突。",
    }
    return mapping.get(genre, "按题材常见阅读预期组织语言和节奏，但仍以具体场景、具体动作和具体后果优先。")


def genre_style_exemplars(genre: str) -> str:
    mapping = {
        "romance": (
            "参考这种质感：情绪藏在动作迟疑、话说一半、视线回避、误会没有立刻说开里；"
            "关系推进靠互动温差，不靠直白表白总结。"
        ),
        "fantasy": (
            "参考这种质感：异象先落在触感、光线、声音和代价上，再带出规则；"
            "世界观通过人物应对显现，不单独停下来讲设定。"
        ),
        "horror": (
            "参考这种质感：先有不对劲的小地方，再让角色确认自己是不是看错；"
            "恐惧从细节累积，不靠大喊危险或直接解释来源。"
        ),
        "sci_fi": (
            "参考这种质感：技术先改变决策和风险，再暴露概念；"
            "冲突来自系统限制、信息偏差和现实后果，不是术语堆砌。"
        ),
        "suspense": (
            "参考这种质感：线索每次只多开一条缝，人物判断可以失手但必须有依据；"
            "悬念靠证据推进，不靠作者故意捂住信息。"
        ),
        "urban": (
            "参考这种质感：说话方式接近日常，场景里要有具体生活阻力和空间细节；"
            "情绪落在小动作和现场反应，不飘在空中。"
        ),
        "slice_of_life": (
            "参考这种质感：把人物关系写进吃饭、等车、收拾房间、顺手一句话这些日常动作；"
            "波澜可以很小，但情绪要真。"
        ),
    }
    return mapping.get(genre, "参考这种质感：先写眼前发生的事，再让情绪和判断从动作里自己浮出来，不要先讲道理。")


def genre_required_elements(genre: str) -> str:
    mapping = {
        "fantasy": "必须让冲突由异象、超常规则、古老秩序、代价交换或非现实环境驱动，场景里要看得见世界法则的反应。",
        "xianxia": "必须让境界、因果、机缘、法宝、宗门秩序或修行代价直接驱动剧情推进。",
        "cultivation": "必须让修行体系、资源争夺、突破代价、传承规则或灵性异变成为主导推进力。",
        "wuxia": "必须让江湖规矩、武学取舍、门派恩怨、身份分寸或招式代价直接决定剧情走向。",
        "sci_fi": "必须让技术限制、系统风险、信息差或现实后果主导冲突，而不是只挂设定名词。",
        "suspense": "必须让线索释放、误导、证据链和判断偏差主导推进。",
        "romance": "必须让关系拉扯、互动温差、误读、承诺代价与情绪变化主导推进。",
    }
    return mapping.get(genre, "必须让当前题材的核心驱动力直接进入场景与行动，而不是只停留在标签层。")


def genre_forbidden_patterns(genre: str) -> str:
    mapping = {
        "fantasy": "禁止写成现代悬疑、刑侦推理、实验室惊悚或硬科幻流程。不得让档案调查、病历检索、控制台操作、数据库追查、机械回收流程成为主导推进方式。",
        "xianxia": "禁止写成现代实验室悬疑、都市职场推理或硬科幻逃生。不得以数据库、实验员、控制台、机械回收作为主线驱动。",
        "cultivation": "禁止写成现代悬疑调查或科技实验事故。不得依赖病历、主控室、监控死角、回收舱、机械追击推动主线。",
        "wuxia": "禁止写成现代都市悬疑或科幻追逃。不得让实验设施、数据库、电子流程压过江湖规则与武学逻辑。",
        "romance": "禁止把主线写成刑侦破案、密室逃脱或硬设定说明。不得让查档案和设备操作压过关系推进。",
    }
    return mapping.get(genre, "禁止串入与当前题材冲突明显的主导类型，不得让外来类型接管主线推进。")


def call_chat_completions(base_url: str, api_key: str, model: str, action: str, context: dict[str, Any]) -> dict[str, Any]:
    endpoint = f"{base_url}/chat/completions"
    contexts = build_request_contexts(action, context)
    raw_payload = ""
    last_error: Exception | None = None
    for context_index, current_context in enumerate(contexts):
        context_mode = "compact" if current_context.get("_retry_mode") == "compact" else "full"
        request_config = action_request_config(action)
        if action == "chapter_draft" and context_index > 0:
            request_config = {"temperature": 0.35, "max_tokens": 3200}
        body = {
            "model": model,
            "temperature": request_config["temperature"],
            "max_tokens": request_config["max_tokens"],
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{build_system_prompt(action)}"
                        f"当前题材补充要求：{genre_style_brief(str(current_context.get('genre', context.get('genre', ''))).strip())}"
                        f" 当前题材正向示例：{genre_style_exemplars(str(current_context.get('genre', context.get('genre', ''))).strip())}"
                        f" 当前题材必须满足：{genre_required_elements(str(current_context.get('genre', context.get('genre', ''))).strip())}"
                        f" 当前题材禁止串台：{genre_forbidden_patterns(str(current_context.get('genre', context.get('genre', ''))).strip())}"
                    ),
                },
                {"role": "user", "content": json.dumps(current_context, ensure_ascii=False)},
            ],
        }
        if DEBUG_ENABLED:
            context_summary = summarize_context_sizes(current_context)
            total_message_chars = sum(len(str(message.get("content", ""))) for message in body["messages"])
            print(
                (
                    f"[agent_runner_openai] request action={action} context_chars={context_summary['context_chars']} "
                    f"context_bytes={context_summary['context_bytes']} message_chars={total_message_chars} "
                    f"largest_fields={context_summary['largest_fields']}"
                ),
                file=sys.stderr,
            )
        for attempt in range(MAX_RETRIES + 1):
            started_at = time.monotonic()
            request = urllib.request.Request(
                endpoint,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "User-Agent": "curl/8.5.0",
                },
                method="POST",
            )
            print(
                (
                    f"[agent_runner_openai] upstream_begin action={action} context_mode={context_mode} "
                    f"attempt={attempt + 1}/{MAX_RETRIES + 1} timeout={UPSTREAM_TIMEOUT_SECONDS} "
                    f"temperature={request_config['temperature']} max_tokens={request_config['max_tokens']}"
                ),
                file=sys.stderr,
            )
            try:
                with urllib.request.urlopen(request, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
                    raw_payload = response.read().decode("utf-8")
                    elapsed = round(time.monotonic() - started_at, 3)
                    print(
                        (
                            f"[agent_runner_openai] upstream_success action={action} context_mode={context_mode} "
                            f"attempt={attempt + 1}/{MAX_RETRIES + 1} elapsed_seconds={elapsed} "
                            f"response_chars={len(raw_payload)}"
                        ),
                        file=sys.stderr,
                    )
                    break
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                retryable = exc.code in {502, 503, 504, 524}
                elapsed = round(time.monotonic() - started_at, 3)
                print(
                    (
                        f"[agent_runner_openai] upstream_http_error action={action} context_mode={context_mode} "
                        f"attempt={attempt + 1}/{MAX_RETRIES + 1} elapsed_seconds={elapsed} "
                        f"status={exc.code} retryable={retryable} error_chars={len(error_body)}"
                    ),
                    file=sys.stderr,
                )
                last_error = RuntimeError(f"http {exc.code}: {error_body}")
                if retryable and attempt < MAX_RETRIES:
                    time.sleep(min(2 * (attempt + 1), 5))
                    continue
                if retryable and context_index + 1 < len(contexts):
                    print(
                        f"[agent_runner_openai] switching_context action={action} from={context_mode} reason=http_{exc.code}",
                        file=sys.stderr,
                    )
                    break
                raise last_error from exc
            except urllib.error.URLError as exc:
                elapsed = round(time.monotonic() - started_at, 3)
                reason = getattr(exc, "reason", exc)
                print(
                    (
                        f"[agent_runner_openai] upstream_url_error action={action} context_mode={context_mode} "
                        f"attempt={attempt + 1}/{MAX_RETRIES + 1} elapsed_seconds={elapsed} reason={reason!r}"
                    ),
                    file=sys.stderr,
                )
                last_error = exc
                if attempt < MAX_RETRIES:
                    time.sleep(min(2 * (attempt + 1), 5))
                    continue
                if context_index + 1 < len(contexts):
                    print(
                        f"[agent_runner_openai] switching_context action={action} from={context_mode} reason=url_error",
                        file=sys.stderr,
                    )
                    break
                raise
        if raw_payload:
            break
    if not raw_payload:
        raise RuntimeError(f"empty upstream response: {last_error}")
    payload = json.loads(raw_payload)
    if DEBUG_ENABLED:
        print(
            f"[agent_runner_openai] action={action} model={model} endpoint={endpoint}",
            file=sys.stderr,
        )
        print(f"[agent_runner_openai] raw_response={raw_payload}", file=sys.stderr)
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("chat completions response is missing message content") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("chat completions returned empty content")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"message content is not valid json: {content}") from exc


def fallback_response(action: str, context: dict[str, Any]) -> dict[str, Any]:
    chapter_index = context.get("chapter_index", 1)
    if action == "chapter_outlines":
        return {
            "_meta": {"fallback": True, "action": action},
            "options": [
                {
                    "option_no": 1,
                    "content": f"第 {chapter_index} 章方案 1：旧线索被重新激活，主角被迫调整判断。",
                    "core_conflict": "主角的既有判断与新出现的证据发生冲突。",
                    "key_event": "一份被忽视的记录暴露出关键矛盾。",
                    "ending_hook": "主角意识到真正的对手可能一直潜伏在身边。",
                    "score_plot": 8.1,
                    "score_consistency": 8.0,
                    "score_hook": 8.2,
                    "final_score": 8.1,
                    "editor_comment": "推进稳定，适合做谨慎转折。",
                },
                {
                    "option_no": 2,
                    "content": f"第 {chapter_index} 章方案 2：公开冲突升级，人物关系被强行推向临界点。",
                    "core_conflict": "主角必须在立场、情感与代价之间立刻做选择。",
                    "key_event": "一场正面交锋迫使隐藏诉求全部浮出水面。",
                    "ending_hook": "冲突结束后留下更大的未知后果。",
                    "score_plot": 8.7,
                    "score_consistency": 8.5,
                    "score_hook": 8.8,
                    "final_score": 8.67,
                    "editor_comment": "节奏强，情绪张力足，适合作为当前章节主线。",
                },
                {
                    "option_no": 3,
                    "content": f"第 {chapter_index} 章方案 3：以支线视角补强世界设定，但主线推进较慢。",
                    "core_conflict": "角色试图理解更大的规则，却暂时无法改写局势。",
                    "key_event": "新的设定信息解释了此前异常现象的来源。",
                    "ending_hook": "角色察觉设定背后还有更深一层操控。",
                    "score_plot": 7.8,
                    "score_consistency": 8.2,
                    "score_hook": 7.7,
                    "final_score": 7.9,
                    "editor_comment": "信息量充足，但需要谨慎控制节奏。",
                },
            ]
        }
    if action == "chapter_review":
        return {
            "_meta": {"fallback": True, "action": action},
            "score_readability": 8.0,
            "score_tension": 8.1,
            "score_consistency": 8.2,
            "final_score": 8.1,
            "issue_summary": "整体可读性稳定，情绪推进自然，但结尾钩子还可以更锋利。",
        }
    if action in {"chapter_draft", "chapter_rewrite", "chapter_expand"}:
        chapter_content = context.get("chapter_content")
        if isinstance(chapter_content, str) and chapter_content.strip():
            return {"_meta": {"fallback": True, "action": action}, "text": chapter_content}
        return {"_meta": {"fallback": True, "action": action}, "text": "内容生成失败，已返回兜底文本。"}
    if action == "project_foundation":
        title = str(context.get("title") or "未命名项目").strip()
        genre = str(context.get("genre") or "fantasy").strip()
        defaults = {
            "fantasy": {
                "summary": f"{title}围绕失落王权、代价魔法与埋藏真相展开。",
                "character_cards": ["背负秘密的主角", "立场摇摆的盟友", "潜伏已久的对手"],
                "world_rules": ["力量使用必须付出代价", "古老誓约会反噬违背者"],
                "event_summary": ["一条旧线索重新浮出水面", "主角被迫卷入更大的权力冲突"],
            },
            "romance": {
                "summary": f"{title}围绕关系拉扯、情感选择与现实代价推进故事。",
                "character_cards": ["克制隐忍的主角", "难以读懂真实心意的对象", "推动关系变化的关键配角"],
                "world_rules": ["情感承诺会改变现实关系结构", "过去的误解会持续影响当下选择"],
                "event_summary": ["一次意外重逢打破原有秩序", "旧关系的裂痕被重新揭开"],
            },
            "horror": {
                "summary": f"{title}以未知威胁逐步逼近的方式展开，角色在恐惧中逼近真相。",
                "character_cards": ["最先察觉异常的主角", "隐瞒部分真相的见证者", "可能成为突破口的同伴"],
                "world_rules": ["异常不会无缘无故出现", "知道得越多越容易被盯上"],
                "event_summary": ["一起诡异事件打破日常", "旧记录与新灾异出现呼应"],
            },
        }.get(
            genre,
            {
                "summary": f"{title}围绕角色目标、外部冲突与升级代价展开。",
                "character_cards": ["核心主角", "关键盟友", "主要对立者"],
                "world_rules": ["世界运转存在清晰限制", "关键选择会持续改变局势"],
                "event_summary": ["故事从一次异常变化开始", "角色迅速卷入更大冲突"],
            },
        )
        return {"_meta": {"fallback": True, "action": action}, **defaults}
    raise RuntimeError(f"unsupported action: {action}")


def main() -> int:
    raw = sys.stdin.read()
    payload = json.loads(raw)
    action = payload["action"]
    context = payload["context"]
    print(
        (
            f"[agent_runner_openai] start action={action} "
            f"base_url={DEFAULT_BASE_URL or '<empty>'} model={DEFAULT_MODEL or '<empty>'} "
            f"api_key_present={bool(DEFAULT_API_KEY)} timeout={UPSTREAM_TIMEOUT_SECONDS} retries={MAX_RETRIES}"
        ),
        file=sys.stderr,
    )

    if not DEFAULT_API_KEY:
        print("[agent_runner_openai] CODEX_API_KEY is empty, using fallback", file=sys.stderr)
        result = fallback_response(action, context)
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
        return 0

    try:
        result = call_chat_completions(
            base_url=DEFAULT_BASE_URL,
            api_key=DEFAULT_API_KEY,
            model=DEFAULT_MODEL,
            action=action,
            context=context,
        )
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        print(
            f"[agent_runner_openai] fallback triggered: {exc}",
            file=sys.stderr,
        )
        result = fallback_response(action, context)

    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
