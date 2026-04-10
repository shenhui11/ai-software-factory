#!/usr/bin/env bash
set -Eeuo pipefail

FEATURE_ID="${1:-FEAT-0001}"

fail_if_illegal_root_dirs_exist() {
  for dir in prd architecture test-plan test-cases; do
    if [[ -d "$dir" ]]; then
      echo "[ERROR] 非法目录: $dir"
      exit 1
    fi
  done
}

echo "===== PRECHECK ====="

test -f "specs/intake/${FEATURE_ID}.json"

echo "===== DESIGN ====="

codex exec "$(sed "s/{feature_id}/${FEATURE_ID}/g" specs/prompts/product-manager.md)"
codex exec "$(sed "s/{feature_id}/${FEATURE_ID}/g" specs/prompts/architect.md)"
codex exec "$(sed "s/{feature_id}/${FEATURE_ID}/g" specs/prompts/test-designer.md)"

echo "===== VERIFY DESIGN ====="

test -s "specs/prd/${FEATURE_ID}.md"
test -s "specs/architecture/${FEATURE_ID}.md"
test -s "specs/test-plan/${FEATURE_ID}.md"
test -s "specs/test-cases/${FEATURE_ID}.yaml"

fail_if_illegal_root_dirs_exist

echo "===== BUILD ====="

codex exec "$(sed "s/{feature_id}/${FEATURE_ID}/g" specs/prompts/builder.strict.md)"

echo "===== VERIFY BUILD ====="

find apps -type f | grep -q .
find tests -type f | grep -q .

fail_if_illegal_root_dirs_exist

echo "===== TEST ====="

python -m pytest tests -q

echo "===== DONE ====="
