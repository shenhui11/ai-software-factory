import json
import sys
import yaml

feature_id = sys.argv[1]
spec_path = f"specs/intake/{feature_id}.json"
out_path = f"specs/test-cases/{feature_id}.yaml"

with open(spec_path, "r", encoding="utf-8") as f:
    spec = json.load(f)

cases = {
    "feature_id": feature_id,
    "unit": [{"name": f"unit_{i+1}", "covers": item} for i, item in enumerate(spec.get("test_strategy", {}).get("unit", []))],
    "integration": [{"name": f"integration_{i+1}", "covers": item} for i, item in enumerate(spec.get("test_strategy", {}).get("integration", []))],
    "e2e": [{"name": f"e2e_{i+1}", "covers": item} for i, item in enumerate(spec.get("test_strategy", {}).get("e2e", []))]
}

with open(out_path, "w", encoding="utf-8") as f:
    yaml.safe_dump(cases, f, allow_unicode=True, sort_keys=False)

print(f"Generated {out_path}")
