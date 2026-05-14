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

    requirement_card_path = Path(f"specs/requirement-card/{feature_id}.md")
    intake_path = Path(f"specs/intake/{feature_id}.json")

    requirement_card_text = ""
    if requirement_card_path.exists():
        requirement_card_text = requirement_card_path.read_text(encoding="utf-8")

    data = {
        "feature_id": feature_id,
        "raw_requirement": raw_requirement,
        "requirement_card_file": f"specs/requirement-card/{feature_id}.md",
        "manual_guidance": [],
        "product_context": {
            "target_users": [],
            "business_goal": "",
            "problem_statement": "",
            "success_metrics": []
        },
        "mvp_scope": [],
        "out_of_scope": [],
        "assumptions": [],
        "open_questions": [],
        "constraints": {
            "tech_stack": ["FastAPI", "pytest"],
            "non_functional": {
                "security": [],
                "performance": [],
                "reliability": [],
                "observability": []
            }
        },
        "actors": [],
        "acceptance_criteria": [],
        "notes": requirement_card_text[:4000]
    }

    intake_path.parent.mkdir(parents=True, exist_ok=True)
    intake_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"Generated {intake_path}")


if __name__ == "__main__":
    main()
