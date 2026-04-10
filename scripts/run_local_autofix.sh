#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

test -f "specs/prompts/auto-fix.strict.md"
test -f "AGENTS.md"

codex exec --skip-git-repo-check "$(cat specs/prompts/auto-fix.strict.md)"

python -m pytest tests -q
