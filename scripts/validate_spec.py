import json
import sys
from jsonschema import validate

spec_file = sys.argv[1]
schema_file = sys.argv[2]

with open(spec_file, "r", encoding="utf-8") as f:
    spec = json.load(f)

with open(schema_file, "r", encoding="utf-8") as f:
    schema = json.load(f)

validate(instance=spec, schema=schema)
print("Spec validation passed.")
