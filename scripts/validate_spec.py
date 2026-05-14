import argparse
import json
from pathlib import Path

from jsonschema import validate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_file")
    parser.add_argument("schema_file")
    args = parser.parse_args()

    spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8"))
    schema = json.loads(Path(args.schema_file).read_text(encoding="utf-8"))

    validate(instance=spec, schema=schema)
    print(f"Validated {args.spec_file} against {args.schema_file}")


if __name__ == "__main__":
    main()
