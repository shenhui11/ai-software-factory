#!/usr/bin/env bash
set -Eeuo pipefail

FEATURE_ID="${1:-FEAT-0001}"
RAW_REQUIREMENT="${2:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

require_file() {
  local path="$1"
  [[ -f "$path" ]] || { echo "[ERROR] 缺少文件: $path"; exit 1; }
}

require_non_empty_file() {
  local path="$1"
  require_file "$path"
  [[ -s "$path" ]] || { echo "[ERROR] 文件为空: $path"; exit 1; }
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

if [[ -z "$RAW_REQUIREMENT" ]]; then
  echo "[ERROR] 请提供原始需求"
  echo "用法: bash scripts/run_local_intake.sh FEAT-0001 \"一句话需求\""
  exit 1
fi

echo "===== PRECHECK ====="
echo "ROOT_DIR=$ROOT_DIR"
echo "FEATURE_ID=$FEATURE_ID"
echo "RAW_REQUIREMENT=$RAW_REQUIREMENT"

command_exists codex || { echo "[ERROR] codex 不在 PATH 中"; exit 1; }
command_exists python || { echo "[ERROR] python 不在 PATH 中"; exit 1; }

require_file "AGENTS.md"
require_file "specs/prompts/brainstorm.md"
require_file "specs/prompts/solution-structurer.md"
require_file "specs/prompts/scoring.md"
require_file "specs/prompts/decision.md"
require_file "scripts/generate_spec.py"
require_file "scripts/validate_spec.py"
require_file "specs/schema/feature-spec.schema.json"

mkdir -p specs/brainstorm specs/scoring specs/decision specs/intake

echo "===== WRITE CHECK ====="
WRITE_CHECK_FILE=".codex_write_check.tmp"
rm -f "$WRITE_CHECK_FILE"
printf 'write-check\n' > "$WRITE_CHECK_FILE"
test -f "$WRITE_CHECK_FILE"
rm -f "$WRITE_CHECK_FILE"

echo "===== BRAINSTORM ====="
BRAINSTORM_PROMPT="$(sed "s/{feature_id}/${FEATURE_ID}/g" specs/prompts/brainstorm.md)"
BRAINSTORM_PROMPT="${BRAINSTORM_PROMPT}"$'\n\n'"原始需求：${RAW_REQUIREMENT}"
codex exec --skip-git-repo-check "$BRAINSTORM_PROMPT"

echo "===== STRUCTURE SOLUTIONS ====="
STRUCTURER_PROMPT="$(sed "s/{feature_id}/${FEATURE_ID}/g" specs/prompts/solution-structurer.md)"
codex exec --skip-git-repo-check "$STRUCTURER_PROMPT"

echo "===== SCORE SOLUTIONS ====="
SCORING_PROMPT="$(sed "s/{feature_id}/${FEATURE_ID}/g" specs/prompts/scoring.md)"
codex exec --skip-git-repo-check "$SCORING_PROMPT"

echo "===== DECISION ====="
DECISION_PROMPT="$(sed "s/{feature_id}/${FEATURE_ID}/g" specs/prompts/decision.md)"
codex exec --skip-git-repo-check "$DECISION_PROMPT"

echo "===== VERIFY DECISION ARTIFACTS ====="
require_non_empty_file "specs/brainstorm/${FEATURE_ID}.md"
require_non_empty_file "specs/scoring/${FEATURE_ID}.json"
require_non_empty_file "specs/decision/${FEATURE_ID}.md"

echo "===== GENERATE INTAKE JSON ====="
python scripts/generate_spec.py \
  --feature_id "${FEATURE_ID}" \
  --requirement "${RAW_REQUIREMENT}"

echo "===== VALIDATE INTAKE JSON ====="
python scripts/validate_spec.py \
  "specs/intake/${FEATURE_ID}.json" \
  "specs/schema/feature-spec.schema.json"

echo "===== SHOW OUTPUTS ====="
wc -c \
  "specs/brainstorm/${FEATURE_ID}.md" \
  "specs/scoring/${FEATURE_ID}.json" \
  "specs/decision/${FEATURE_ID}.md" \
  "specs/intake/${FEATURE_ID}.json"

echo "===== DONE ====="
