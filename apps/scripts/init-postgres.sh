#!/usr/bin/env sh
set -eu

DB_NAME="${1:-ai_software_factory}"
SCHEMA_FILE="$(dirname "$0")/../backend/sql/postgres_schema.sql"

if [ -z "${PGHOST:-}" ] || [ -z "${PGUSER:-}" ] || [ -z "${PGPASSWORD:-}" ]; then
  echo "Set PGHOST, PGUSER, and PGPASSWORD first." >&2
  exit 1
fi

if ! pg_isready -h "${PGHOST}" -p "${PGPORT:-5432}" -U "${PGUSER}" >/dev/null 2>&1; then
  echo "PostgreSQL is not reachable at ${PGHOST}:${PGPORT:-5432}." >&2
  exit 2
fi

psql -h "${PGHOST}" -p "${PGPORT:-5432}" -U "${PGUSER}" -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}') THEN
        EXECUTE format('CREATE DATABASE %I', '${DB_NAME}');
    END IF;
END
\$\$;
SQL

psql -h "${PGHOST}" -p "${PGPORT:-5432}" -U "${PGUSER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -f "${SCHEMA_FILE}"
