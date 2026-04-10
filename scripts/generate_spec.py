import argparse
import json
import re
from pathlib import Path
from typing import Any


def read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_selected_solution(decision_text: str, scoring_data: dict[str, Any]) -> dict[str, str]:
    top_solution_id = scoring_data.get("top_solution_id", "").strip()
    solutions = {item.get("id", ""): item for item in scoring_data.get("solutions", [])}

    selected = {
        "id": top_solution_id or "solution_1",
        "name": "待补充",
        "reason": "待补充",
    }

    if top_solution_id and top_solution_id in solutions:
        selected["name"] = str(solutions[top_solution_id].get("name", "待补充"))

    # 从 decision 文本里尽量提取“选择理由”
    # 简单策略：找“选择理由/原因”相关行
    reason_patterns = [
        r"选择理由[:：]\s*(.+)",
        r"推荐理由[:：]\s*(.+)",
        r"原因[:：]\s*(.+)",
    ]
    for pattern in reason_patterns:
        match = re.search(pattern, decision_text)
        if match:
            selected["reason"] = match.group(1).strip()
            break

    return selected


def extract_bullets_after_header(text: str, header_keywords: list[str]) -> list[str]:
    lines = text.splitlines()
    collected: list[str] = []
    capture = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if capture and collected:
                break
            continue

        if any(keyword in stripped for keyword in header_keywords):
            capture = True
            continue

        if capture:
            if re.match(r"^#{1,6}\s+", stripped):
                break
            if re.match(r"^\d+[.)、]\s+", stripped):
                item = re.sub(r"^\d+[.)、]\s+", "", stripped).strip()
                collected.append(item)
            elif re.match(r"^[-*]\s+", stripped):
                item = re.sub(r"^[-*]\s+", "", stripped).strip()
                collected.append(item)
            else:
                # 遇到普通文本时，如果已经收集过，就停止；否则跳过
                if collected:
                    break

    return collected


def build_intake_json(
    feature_id: str,
    raw_requirement: str,
    scoring_data: dict[str, Any],
    decision_text: str,
) -> dict[str, Any]:
    selected_solution = extract_selected_solution(decision_text, scoring_data)

    mvp_scope = extract_bullets_after_header(decision_text, ["MVP", "MVP 范围", "最小可用范围"])
    out_of_scope = extract_bullets_after_header(decision_text, ["Out of scope", "不做什么", "本轮不做"])

    actors: list[str] = []
    acceptance_criteria: list[str] = []

    # 如果 decision 里没提取出来，给出保底占位，避免后面完全空
    if not mvp_scope:
        mvp_scope = ["待从 decision 结果中补充 MVP 范围"]

    intake = {
        "feature_id": feature_id,
        "raw_requirement": raw_requirement,
        "selected_solution": selected_solution,
        "mvp_scope": mvp_scope,
        "out_of_scope": out_of_scope,
        "actors": actors,
        "constraints": {
            "tech_stack": ["FastAPI", "pytest"],
            "non_functional": {
                "security": [],
                "performance": [],
                "reliability": [],
                "observability": [],
            },
        },
        "acceptance_criteria": acceptance_criteria,
        "decision_artifacts": {
            "brainstorm_file": f"specs/brainstorm/{feature_id}.md",
            "scoring_file": f"specs/scoring/{feature_id}.json",
            "decision_file": f"specs/decision/{feature_id}.md",
        },
    }

    return intake


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate intake spec from product decision artifacts.")
    parser.add_argument("--feature_id", required=True, help="Feature ID, e.g. FEAT-0001")
    parser.add_argument("--requirement", required=True, help="Raw requirement text")
    args = parser.parse_args()

    feature_id = args.feature_id.strip()
    raw_requirement = args.requirement.strip()

    scoring_file = Path(f"specs/scoring/{feature_id}.json")
    decision_file = Path(f"specs/decision/{feature_id}.md")
    intake_file = Path(f"specs/intake/{feature_id}.json")

    scoring_data = read_json_file(scoring_file)
    decision_text = read_text_file(decision_file)

    intake_data = build_intake_json(
        feature_id=feature_id,
        raw_requirement=raw_requirement,
        scoring_data=scoring_data,
        decision_text=decision_text,
    )

    intake_file.parent.mkdir(parents=True, exist_ok=True)
    with intake_file.open("w", encoding="utf-8") as f:
        json.dump(intake_data, f, ensure_ascii=False, indent=2)

    print(f"Generated {intake_file}")


if __name__ == "__main__":
    main()


