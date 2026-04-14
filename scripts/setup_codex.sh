#!/usr/bin/env bash
set -Eeuo pipefail

: "${CODEX_BASE_URL:?CODEX_BASE_URL is required}"

mkdir -p ~/.codex

cat > ~/.codex/config.toml <<EOF
model = "gpt-5.4"
model_reasoning_effort = "low"
model_provider = "newapi"
approval_policy = "never"
sandbox_mode = "danger-full-access"

[model_providers.newapi]
name = "newapi"
base_url = "${CODEX_BASE_URL}"
wire_api = "responses"
env_key = "CODEX_API_KEY"
EOF

echo "Codex config written to ~/.codex/config.toml"
