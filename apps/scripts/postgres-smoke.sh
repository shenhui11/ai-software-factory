#!/usr/bin/env sh
set -eu

DB_NAME="${1:-ai_software_factory}"

if [ -z "${PGHOST:-}" ] || [ -z "${PGUSER:-}" ] || [ -z "${PGPASSWORD:-}" ]; then
  echo "Set PGHOST, PGUSER, and PGPASSWORD first." >&2
  exit 1
fi

if ! pg_isready -h "${PGHOST}" -p "${PGPORT:-5432}" -U "${PGUSER}"; then
  echo "PostgreSQL is not reachable at ${PGHOST}:${PGPORT:-5432}." >&2
  exit 2
fi

psql -h "${PGHOST}" -p "${PGPORT:-5432}" -U "${PGUSER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 <<'SQL'
SELECT current_database() AS db_name;
SELECT COUNT(*) AS template_count FROM templates;
SELECT COUNT(*) AS membership_plan_count FROM membership_plans;
SELECT COUNT(*) AS safety_policy_count FROM safety_policies;
SELECT COUNT(*) AS app_state_count FROM app_state;
SQL
