from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path

from apps.backend.models import AuthSession, AuthUser, UserRole, new_id


DEFAULT_AUTH_DB_PATH = Path(__file__).resolve().parent / "data" / "auth.db"
PBKDF2_ITERATIONS = 600000
try:  # pragma: no cover - optional dependency
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - keep local tests working without postgres driver
    psycopg = None
    dict_row = None


class SqliteAuthStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or os.getenv("AUTH_DB_PATH", str(DEFAULT_AUTH_DB_PATH)))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )

    def reset_for_tests(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions")
            connection.execute("DELETE FROM users")
            connection.commit()

    def register_user(self, username: str, password: str, role: UserRole) -> AuthUser:
        normalized = _normalize_username(username)
        user_id = new_id("user")
        password_hash = _hash_password(password)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                    (user_id, normalized, password_hash, role.value),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在") from exc
        return AuthUser(id=user_id, username=normalized, role=role)

    def login(self, username: str, password: str) -> AuthSession | None:
        normalized = _normalize_username(username)
        _validate_password(password)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, role FROM users WHERE username = ?",
                (normalized,),
            ).fetchone()
            if not row or not _verify_password(password, row["password_hash"]):
                return None
            token = secrets.token_urlsafe(32)
            connection.execute(
                "INSERT INTO sessions (token, user_id) VALUES (?, ?)",
                (token, row["id"]),
            )
            connection.commit()
        return AuthSession(
            token=token,
            user=AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"])),
        )

    def get_user_by_token(self, token: str) -> AuthUser | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.username, users.role
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()
        if not row:
            return None
        return AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"]))

    def list_users(self) -> list[AuthUser]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, username, role FROM users ORDER BY created_at DESC, username ASC"
            ).fetchall()
        return [AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"])) for row in rows]

    def get_user_by_username(self, username: str) -> AuthUser | None:
        normalized = _normalize_username(username)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, role FROM users WHERE username = ?",
                (normalized,),
            ).fetchone()
        if not row:
            return None
        return AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"]))

    def delete_session(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
            connection.commit()

    def update_password(self, token: str, current_password: str, new_password: str) -> AuthSession:
        _validate_password(current_password)
        new_hash = _hash_password(new_password)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.username, users.password_hash, users.role
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()
            if not row:
                raise ValueError("当前登录状态已失效")
            if not _verify_password(current_password, row["password_hash"]):
                raise ValueError("当前密码不正确")
            connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, row["id"]))
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            next_token = secrets.token_urlsafe(32)
            connection.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (next_token, row["id"]))
            connection.commit()
        return AuthSession(
            token=next_token,
            user=AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"])),
        )

    def admin_reset_password(self, user_id: str, new_password: str) -> AuthUser:
        _validate_password(new_password)
        new_hash = _hash_password(new_password)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, role FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                raise ValueError("用户不存在")
            connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, row["id"]))
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            connection.commit()
        return AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"]))


class PostgresAuthStore:
    def __init__(self, database_url: str) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL auth storage")
        self.database_url = database_url
        self._init_schema()

    def _connect(self):
        connection = psycopg.connect(self.database_url)
        connection.row_factory = dict_row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        token TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            connection.commit()

    def reset_for_tests(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE sessions, users RESTART IDENTITY CASCADE")
            connection.commit()

    def register_user(self, username: str, password: str, role: UserRole) -> AuthUser:
        normalized = _normalize_username(username)
        user_id = new_id("user")
        password_hash = _hash_password(password)
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO users (id, username, password_hash, role) VALUES (%s, %s, %s, %s)",
                        (user_id, normalized, password_hash, role.value),
                    )
                connection.commit()
        except Exception as exc:
            if "duplicate key" in str(exc).lower() or "unique" in str(exc).lower():
                raise ValueError("用户名已存在") from exc
            raise
        return AuthUser(id=user_id, username=normalized, role=role)

    def login(self, username: str, password: str) -> AuthSession | None:
        normalized = _normalize_username(username)
        _validate_password(password)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username, password_hash, role FROM users WHERE username = %s",
                    (normalized,),
                )
                row = cursor.fetchone()
                if not row or not _verify_password(password, row["password_hash"]):
                    return None
                token = secrets.token_urlsafe(32)
                cursor.execute(
                    "INSERT INTO sessions (token, user_id) VALUES (%s, %s)",
                    (token, row["id"]),
                )
            connection.commit()
        return AuthSession(
            token=token,
            user=AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"])),
        )

    def get_user_by_token(self, token: str) -> AuthUser | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT users.id, users.username, users.role
                    FROM sessions
                    JOIN users ON users.id = sessions.user_id
                    WHERE sessions.token = %s
                    """,
                    (token,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"]))

    def list_users(self) -> list[AuthUser]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username, role FROM users ORDER BY created_at DESC, username ASC"
                )
                rows = cursor.fetchall()
        return [AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"])) for row in rows]

    def get_user_by_username(self, username: str) -> AuthUser | None:
        normalized = _normalize_username(username)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username, role FROM users WHERE username = %s",
                    (normalized,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"]))

    def delete_session(self, token: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM sessions WHERE token = %s", (token,))
            connection.commit()

    def update_password(self, token: str, current_password: str, new_password: str) -> AuthSession:
        _validate_password(current_password)
        new_hash = _hash_password(new_password)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT users.id, users.username, users.password_hash, users.role
                    FROM sessions
                    JOIN users ON users.id = sessions.user_id
                    WHERE sessions.token = %s
                    """,
                    (token,),
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError("当前登录状态已失效")
                if not _verify_password(current_password, row["password_hash"]):
                    raise ValueError("当前密码不正确")
                cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, row["id"]))
                cursor.execute("DELETE FROM sessions WHERE user_id = %s", (row["id"],))
                next_token = secrets.token_urlsafe(32)
                cursor.execute("INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (next_token, row["id"]))
            connection.commit()
        return AuthSession(
            token=next_token,
            user=AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"])),
        )

    def admin_reset_password(self, user_id: str, new_password: str) -> AuthUser:
        _validate_password(new_password)
        new_hash = _hash_password(new_password)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username, role FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError("用户不存在")
                cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, row["id"]))
                cursor.execute("DELETE FROM sessions WHERE user_id = %s", (row["id"],))
            connection.commit()
        return AuthUser(id=row["id"], username=row["username"], role=UserRole(row["role"]))


def build_auth_store():
    backend = os.getenv("AUTH_STORAGE_BACKEND", "").strip().lower() or os.getenv("APP_STORAGE_BACKEND", "").strip().lower()
    database_url = os.getenv("AUTH_DATABASE_URL", "").strip() or os.getenv("APP_DATABASE_URL", "").strip()
    if backend == "sqlite":
        return SqliteAuthStore()
    if database_url:
        return PostgresAuthStore(database_url)
    raise RuntimeError(
        "PostgreSQL storage is required by default. Set AUTH_DATABASE_URL or APP_DATABASE_URL. "
        "Use AUTH_STORAGE_BACKEND=sqlite only for explicit local/test fallback."
    )


def _normalize_username(username: str) -> str:
    normalized = username.strip()
    if not normalized:
        raise ValueError("用户名不能为空")
    if len(normalized) > 50:
        raise ValueError("用户名长度不能超过 50 个字符")
    return normalized


def _validate_password(password: str) -> None:
    if len(password) < 6:
        raise ValueError("密码长度不能少于 6 位")


def _hash_password(password: str) -> str:
    _validate_password(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("pbkdf2_sha256$"):
        _, raw_iterations, salt, expected_digest = stored_hash.split("$", 3)
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(raw_iterations),
        ).hex()
        return hmac.compare_digest(actual_digest, expected_digest)
    legacy_digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_digest, stored_hash)
