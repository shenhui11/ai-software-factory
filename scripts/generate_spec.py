import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature_id", required=True)
    parser.add_argument("--requirement", required=True)
    args = parser.parse_args()

    feature_id = args.feature_id.strip()
    raw_requirement = args.requirement.strip()

    decision_path = Path(f"specs/decision/{feature_id}.md")
    intake_path = Path(f"specs/intake/{feature_id}.json")

    decision_text = ""
    if decision_path.exists():
        decision_text = decision_path.read_text(encoding="utf-8")

    data = {
        "feature_id": feature_id,
        "raw_requirement": raw_requirement,
        "manual_guidance": [],
        "selected_solution": {
            "id": "solution_1",
            "name": "待人工确认",
            "reason": "待人工确认"
        },
        "mvp_scope": ["待人工确认"],
        "out_of_scope": [],
        "actors": [],
        "constraints": {
            "tech_stack": ["FastAPI", "pytest"],
            "non_functional": {
                "security": [],
                "performance": [],
                "reliability": [],
                "observability": []
            }
        },
        "acceptance_criteria": [],
        "decision_artifacts": {
            "requirement_card_file": f"specs/requirement-card/{feature_id}.md",
            "decision_file": f"specs/decision/{feature_id}.md"
        },
        "notes": decision_text[:2000]
    }

    intake_path.parent.mkdir(parents=True, exist_ok=True)
    intake_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {intake_path}")


if __name__ == "__main__":
    main()

