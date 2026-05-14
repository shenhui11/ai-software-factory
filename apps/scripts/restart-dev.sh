#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_ENV_FILE="${ROOT_DIR}/apps/scripts/.env.local"
BACKEND_PORT=8000
LEGACY_FRONTEND_PORT=5137
FRONTEND_PORT=5173
BACKEND_LOG="/tmp/ai-software-factory-backend.log"
FRONTEND_LOG="/tmp/ai-software-factory-frontend.log"
BACKEND_PID_FILE="/tmp/ai-software-factory-backend.pid"
FRONTEND_PID_FILE="/tmp/ai-software-factory-frontend.pid"
PUBLIC_FRONTEND_URL="${PUBLIC_FRONTEND_URL:-}"
PUBLIC_BACKEND_URL="${PUBLIC_BACKEND_URL:-}"

clear_frontend_api_override() {
  if [[ -n "${VITE_API_BASE_URL:-}" ]]; then
    echo "clearing VITE_API_BASE_URL from current shell to force Vite proxy mode"
    unset VITE_API_BASE_URL
  fi
}

load_local_env() {
  if [[ -f "${SCRIPT_ENV_FILE}" ]]; then
    echo "loading local env from ${SCRIPT_ENV_FILE}"
    set -a
    # shellcheck disable=SC1090
    source "${SCRIPT_ENV_FILE}"
    set +a
  fi
}

require_database_config() {
  local backend="${APP_STORAGE_BACKEND:-}"
  local auth_backend="${AUTH_STORAGE_BACKEND:-}"
  local app_db="${APP_DATABASE_URL:-}"
  local auth_db="${AUTH_DATABASE_URL:-}"

  if [[ "${backend}" == "sqlite" || "${auth_backend}" == "sqlite" ]]; then
    echo "sqlite fallback enabled explicitly; skipping PostgreSQL config check"
    return
  fi

  if [[ -n "${app_db}" || -n "${auth_db}" ]]; then
    return
  fi

  echo "missing database config: set APP_DATABASE_URL or AUTH_DATABASE_URL" >&2
  echo "you can place them in ${SCRIPT_ENV_FILE} before running this script" >&2
  exit 1
}

require_postgres_driver() {
  local backend="${APP_STORAGE_BACKEND:-}"
  local auth_backend="${AUTH_STORAGE_BACKEND:-}"

  if [[ "${backend}" == "sqlite" || "${auth_backend}" == "sqlite" ]]; then
    return
  fi

  if ./venv/bin/python -c "import psycopg" >/dev/null 2>&1; then
    return
  fi

  echo "missing Python package: psycopg" >&2
  echo "run: ./venv/bin/pip install -r requirements.txt" >&2
  exit 1
}

port_pids() {
  local port="$1"
  lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
}

port_in_use() {
  local port="$1"
  [[ -n "$(port_pids "${port}")" ]]
}

print_port_status() {
  local port="$1"
  local pids
  pids="$(port_pids "${port}")"
  if [[ -n "${pids}" ]]; then
    echo "port ${port} is in use by PID(s): ${pids//$'\n'/, }"
  else
    echo "port ${port} is free"
  fi
}

kill_port() {
  local port="$1"
  local pids
  pids="$(port_pids "${port}")"
  if [[ -z "${pids}" ]]; then
    echo "no process is listening on port ${port}"
    return
  fi

  echo "stopping process(es) on port ${port}: ${pids//$'\n'/, }"
  kill ${pids} 2>/dev/null || true

  for _ in {1..10}; do
    if ! port_in_use "${port}"; then
      echo "port ${port} is now free"
      return
    fi
    sleep 1
  done

  pids="$(port_pids "${port}")"
  if [[ -n "${pids}" ]]; then
    echo "force killing process(es) on port ${port}: ${pids//$'\n'/, }"
    kill -9 ${pids} 2>/dev/null || true
  fi

  sleep 1
  if port_in_use "${port}"; then
    echo "failed to free port ${port}" >&2
    exit 1
  fi
}

assert_port_free() {
  local port="$1"
  if port_in_use "${port}"; then
    echo "port ${port} is still occupied, aborting startup" >&2
    print_port_status "${port}" >&2
    exit 1
  fi
}

start_backend() {
  echo "starting backend on port ${BACKEND_PORT}"
  cd "${ROOT_DIR}"
  echo "backend agent runner command: ${AGENT_RUNNER_COMMAND:-<empty>}"
  echo "backend agent runner url: ${AGENT_RUNNER_URL:-<empty>}"
  if [[ -n "${CODEX_API_KEY:-}" ]]; then
    echo "backend codex api key: <present>"
  else
    echo "backend codex api key: <empty>"
  fi
  echo "backend codex base url: ${CODEX_BASE_URL:-<empty>}"
  echo "backend codex model: ${CODEX_MODEL:-<empty>}"
  echo "backend codex timeout seconds: ${CODEX_TIMEOUT_SECONDS:-<empty>}"
  echo "backend codex retry attempts: ${CODEX_RETRY_ATTEMPTS:-<empty>}"
  echo "backend agent runner timeout seconds: ${AGENT_RUNNER_TIMEOUT_SECONDS:-<empty>}"
  nohup env \
    AGENT_RUNNER_COMMAND="${AGENT_RUNNER_COMMAND:-}" \
    AGENT_RUNNER_URL="${AGENT_RUNNER_URL:-}" \
    CODEX_API_KEY="${CODEX_API_KEY:-}" \
    CODEX_BASE_URL="${CODEX_BASE_URL:-}" \
    CODEX_MODEL="${CODEX_MODEL:-}" \
    CODEX_TIMEOUT_SECONDS="${CODEX_TIMEOUT_SECONDS:-}" \
    CODEX_RETRY_ATTEMPTS="${CODEX_RETRY_ATTEMPTS:-}" \
    AGENT_RUNNER_DEBUG="${AGENT_RUNNER_DEBUG:-}" \
    AGENT_RUNNER_TIMEOUT_SECONDS="${AGENT_RUNNER_TIMEOUT_SECONDS:-}" \
    uvicorn apps.backend.main:app --host 0.0.0.0 --port "${BACKEND_PORT}" >"${BACKEND_LOG}" 2>&1 &
  echo $! > "${BACKEND_PID_FILE}"
}

start_frontend() {
  echo "starting frontend on port ${FRONTEND_PORT}"
  echo "frontend api mode: Vite proxy (/api,/admin,/health -> http://127.0.0.1:${BACKEND_PORT})"
  cd "${ROOT_DIR}/apps/web"
  nohup env -u VITE_API_BASE_URL npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}" >"${FRONTEND_LOG}" 2>&1 &
  echo $! > "${FRONTEND_PID_FILE}"
}

wait_for_port() {
  local port="$1"
  local name="$2"
  for _ in {1..20}; do
    if port_in_use "${port}"; then
      echo "${name} is listening on port ${port}"
      return
    fi
    sleep 1
  done
  echo "${name} did not start on port ${port}" >&2
  exit 1
}

echo "checking current port usage"
load_local_env
clear_frontend_api_override
require_database_config
require_postgres_driver
print_port_status "${BACKEND_PORT}"
print_port_status "${LEGACY_FRONTEND_PORT}"
print_port_status "${FRONTEND_PORT}"

kill_port "${BACKEND_PORT}"
kill_port "${LEGACY_FRONTEND_PORT}"
kill_port "${FRONTEND_PORT}"

echo "verifying ports before startup"
assert_port_free "${BACKEND_PORT}"
assert_port_free "${FRONTEND_PORT}"

start_backend
start_frontend

wait_for_port "${BACKEND_PORT}" "backend"
wait_for_port "${FRONTEND_PORT}" "frontend"

echo "restart completed"
echo "backend log: ${BACKEND_LOG}"
echo "frontend log: ${FRONTEND_LOG}"
echo "local frontend: http://127.0.0.1:${FRONTEND_PORT}/"
echo "local backend: http://127.0.0.1:${BACKEND_PORT}/"
echo "frontend proxy: /api,/admin,/health -> http://127.0.0.1:${BACKEND_PORT}"
if [[ -n "${PUBLIC_FRONTEND_URL}" ]]; then
  echo "public frontend: ${PUBLIC_FRONTEND_URL}"
fi
if [[ -n "${PUBLIC_BACKEND_URL}" ]]; then
  echo "public backend: ${PUBLIC_BACKEND_URL}"
fi
