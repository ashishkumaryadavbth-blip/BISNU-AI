from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

from bisnu_x.config import ROOT, settings


DB_PATH = (
    Path(settings.database)
    if Path(settings.database).is_absolute()
    else ROOT / settings.database
)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
REQUIRE_PERSISTENT_DATABASE = (
    os.getenv("BISNU_REQUIRE_PERSISTENT_DB", "").strip().lower()
    in {"1", "true", "yes", "on"}
)


class UsernameTakenError(Exception):
    pass


class DatabaseHealthError(RuntimeError):
    pass


class PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _translate(statement: str) -> str:
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            return "BEGIN"

        ignore_conflicts = bool(
            re.search(
                r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
                statement,
                flags=re.IGNORECASE,
            )
        )
        statement = re.sub(
            r"\binstr\s*\(\s*lower\s*\(\s*text\s*\)\s*,\s*"
            r"lower\s*\(\s*\?\s*\)\s*\)\s*>\s*0",
            "POSITION(LOWER(?) IN LOWER(text)) > 0",
            statement,
            flags=re.IGNORECASE,
        )
        statement = re.sub(
            r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
            "INSERT INTO",
            statement,
            flags=re.IGNORECASE,
        )
        statement = re.sub(
            r"\bINSERT\s+OR\s+REPLACE\s+INTO\s+revoked_tokens\b",
            "INSERT INTO revoked_tokens",
            statement,
            flags=re.IGNORECASE,
        )
        if statement.lstrip().upper().startswith(
            "INSERT INTO REVOKED_TOKENS"
        ):
            statement = statement.rstrip().rstrip(";") + (
                " ON CONFLICT (token_hash) DO UPDATE "
                "SET expires_at = EXCLUDED.expires_at"
            )
        elif ignore_conflicts:
            statement = statement.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return statement.replace("?", "%s")

    def execute(self, statement: str, parameters=()):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            self._connection.execute("BEGIN")
            self._connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("bisnu_webhook_serialization",),
            )
            return None
        return self._connection.execute(
            self._translate(statement),
            parameters,
        )

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def connection():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        return PostgresConnection(
            psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row,
                connect_timeout=10,
            )
        )

    if REQUIRE_PERSISTENT_DATABASE:
        raise RuntimeError(
            "DATABASE_URL is required for this deployment; "
            "refusing to use ephemeral SQLite storage."
        )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def check_database():
    conn = None
    try:
        conn = connection()
        row = conn.execute("SELECT 1 AS healthcheck").fetchone()
        result = (
            row["healthcheck"]
            if isinstance(row, (dict, sqlite3.Row))
            else row[0]
        )
        if result != 1:
            raise RuntimeError("Database health query returned an invalid result.")
        return {
            "backend": "postgresql" if DATABASE_URL else "sqlite",
            "connected": True,
        }
    except Exception as exc:
        raise DatabaseHealthError("Database health check failed.") from exc
    finally:
        if conn is not None:
            conn.close()


def init_db():
    conn = connection()

    schema = """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            name TEXT,
            username TEXT,
            password_hash TEXT,
            picture TEXT,
            plan TEXT NOT NULL DEFAULT 'FREE',
            plan_expires REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT,
            sources TEXT,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            transaction_id TEXT UNIQUE NOT NULL,
            plan TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            user_id TEXT,
            metadata TEXT,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS revoked_tokens (
            token_hash TEXT PRIMARY KEY,
            expires_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider_subscription_id TEXT UNIQUE NOT NULL,
            provider_plan_id TEXT NOT NULL,
            plan TEXT NOT NULL,
            expected_amount INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'INR',
            status TEXT NOT NULL,
            current_end REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_subscriptions_user_updated
        ON subscriptions(user_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS payment_webhook_events (
            event_id TEXT PRIMARY KEY,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_memories_user
        ON user_memories(user_id, created_at DESC);
        """
    if DATABASE_URL:
        try:
            for statement in schema.split(";"):
                statement = statement.strip()
                if statement and not statement.upper().startswith("PRAGMA"):
                    conn.execute(statement)
            conn.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT"
            )
            conn.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT"
            )
            conn.execute(
                """
                UPDATE users AS u
                SET username=NULL
                WHERE u.username IS NOT NULL
                  AND EXISTS (
                    SELECT 1 FROM users AS older
                    WHERE lower(older.username)=lower(u.username)
                      AND older.id < u.id
                  )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique "
                "ON users (LOWER(username)) "
                "WHERE username IS NOT NULL AND username <> ''"
            )
            conn.execute(
                "ALTER TABLE subscriptions "
                "ADD COLUMN IF NOT EXISTS expected_amount "
                "INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute(
                "ALTER TABLE subscriptions "
                "ADD COLUMN IF NOT EXISTS currency "
                "TEXT NOT NULL DEFAULT 'INR'"
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    conn.executescript(schema)

    user_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if "username" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "password_hash" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    conn.execute(
        """
        UPDATE users AS u
        SET username=NULL
        WHERE u.username IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM users AS older
            WHERE lower(older.username)=lower(u.username)
              AND older.id < u.id
          )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique "
        "ON users (LOWER(username)) "
        "WHERE username IS NOT NULL AND username <> ''"
    )
    subscription_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(subscriptions)"
        ).fetchall()
    }
    if "expected_amount" not in subscription_columns:
        conn.execute(
            "ALTER TABLE subscriptions "
            "ADD COLUMN expected_amount INTEGER NOT NULL DEFAULT 0"
        )
    if "currency" not in subscription_columns:
        conn.execute(
            "ALTER TABLE subscriptions "
            "ADD COLUMN currency TEXT NOT NULL DEFAULT 'INR'"
        )

    conn.commit()
    conn.close()


def create_user(
    email: str | None,
    name: str | None,
    picture: str | None = None
):
    user_id = str(uuid.uuid4())
    now = time.time()

    conn = connection()

    conn.execute(
        """
        INSERT INTO users
        (
            id,
            email,
            name,
            picture,
            plan,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 'FREE', ?, ?)
        """,
        (
            user_id,
            email,
            name,
            picture,
            now,
            now
        )
    )

    conn.commit()

    row = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    return dict(row)


def get_user(user_id: str):
    conn = connection()

    row = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    return dict(row) if row else None


def get_user_by_email(email: str):
    conn = connection()

    row = conn.execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
    ).fetchone()

    conn.close()

    return dict(row) if row else None


def get_user_by_username(username: str):
    conn = connection()
    row = conn.execute(
        "SELECT * FROM users WHERE lower(username)=?",
        (username.strip().lower(),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _is_integrity_error(error: Exception) -> bool:
    if isinstance(error, sqlite3.IntegrityError):
        return True
    if DATABASE_URL:
        import psycopg

        return isinstance(error, psycopg.IntegrityError)
    return False


def create_password_user(username: str, password_hash: str):
    user_id = str(uuid.uuid4())
    now = time.time()
    normalized_username = username.strip().lower()
    conn = connection()
    try:
        conn.execute(
            """
            INSERT INTO users
                (id, email, name, username, password_hash, picture,
                 plan, created_at, updated_at)
            VALUES (?, NULL, ?, ?, ?, NULL, 'FREE', ?, ?)
            """,
            (
                user_id,
                normalized_username,
                normalized_username,
                password_hash,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if not row:
            raise RuntimeError("Registered user could not be read back.")
        return dict(row)
    except Exception as exc:
        conn.rollback()
        if _is_integrity_error(exc):
            raise UsernameTakenError from exc
        raise
    finally:
        conn.close()


def set_user_credentials(
    user_id: str,
    username: str,
    password_hash: str,
):
    conn = connection()
    try:
        cursor = conn.execute(
            """
            UPDATE users
            SET username=?, password_hash=?, updated_at=?
            WHERE id=?
            """,
            (
                username.strip().lower(),
                password_hash,
                time.time(),
                user_id,
            ),
        )
        conn.commit()
        return cursor.rowcount == 1
    except Exception as exc:
        conn.rollback()
        if _is_integrity_error(exc):
            raise UsernameTakenError from exc
        raise
    finally:
        conn.close()


def get_or_create_user(
    email: str,
    name: str | None,
    picture: str | None = None
):
    user = get_user_by_email(email)

    if user:
        conn = connection()

        conn.execute(
            """
            UPDATE users
            SET name=?,
                picture=?,
                updated_at=?
            WHERE email=?
            """,
            (
                name,
                picture,
                time.time(),
                email
            )
        )

        conn.commit()

        row = conn.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()

        conn.close()

        return dict(row)

    return create_user(
        email,
        name,
        picture
    )


def update_user_profile(
    user_id: str,
    name: str,
    username: str,
):
    conn = connection()
    try:
        cursor = conn.execute(
            """
            UPDATE users
            SET name=?, username=?, updated_at=?
            WHERE id=?
            """,
            (name, username.strip().lower(), time.time(), user_id),
        )
        conn.commit()
        return cursor.rowcount == 1
    except Exception as exc:
        conn.rollback()
        if _is_integrity_error(exc):
            raise UsernameTakenError from exc
        raise
    finally:
        conn.close()


def add_user_memory(user_id: str, text: str):
    memory_id = str(uuid.uuid4())
    conn = connection()
    conn.execute(
        """
        INSERT INTO user_memories (id, user_id, text, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (memory_id, user_id, text, time.time()),
    )
    conn.commit()
    conn.close()
    return memory_id


def list_user_memories(user_id: str, query: str = ""):
    conn = connection()
    if query.strip():
        rows = conn.execute(
            """
            SELECT id, text, created_at FROM user_memories
            WHERE user_id=? AND instr(lower(text), lower(?)) > 0
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (user_id, query.strip()),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, text, created_at FROM user_memories
            WHERE user_id=?
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_user_memory(user_id: str, memory_id: str):
    conn = connection()
    cursor = conn.execute(
        "DELETE FROM user_memories WHERE id=? AND user_id=?",
        (memory_id, user_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount == 1


def create_conversation(
    user_id: str,
    title: str
):
    cid = str(uuid.uuid4())
    now = time.time()

    conn = connection()

    conn.execute(
        """
        INSERT INTO conversations
        (
            id,
            user_id,
            title,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            cid,
            user_id,
            title[:200],
            now,
            now
        )
    )

    conn.commit()
    conn.close()

    return cid


def list_conversations(user_id: str):
    conn = connection()

    rows = conn.execute(
        """
        SELECT *
        FROM conversations
        WHERE user_id=?
        ORDER BY updated_at DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def conversation_owned(
    conversation_id: str,
    user_id: str
):
    conn = connection()

    row = conn.execute(
        """
        SELECT id
        FROM conversations
        WHERE id=? AND user_id=?
        """,
        (
            conversation_id,
            user_id
        )
    ).fetchone()

    conn.close()

    return bool(row)


def save_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    model: str = "",
    sources=None
):
    mid = str(uuid.uuid4())
    now = time.time()

    if sources is None:
        sources = []

    conn = connection()

    conn.execute(
        """
        INSERT INTO messages
        (
            id,
            conversation_id,
            user_id,
            role,
            content,
            model,
            sources,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mid,
            conversation_id,
            user_id,
            role,
            content,
            model,
            json.dumps(
                sources,
                ensure_ascii=False
            ),
            now
        )
    )

    conn.execute(
        """
        UPDATE conversations
        SET updated_at=?
        WHERE id=? AND user_id=?
        """,
        (
            now,
            conversation_id,
            user_id
        )
    )

    conn.commit()
    conn.close()

    return mid


def get_messages(
    conversation_id: str,
    user_id: str
):
    conn = connection()

    rows = conn.execute(
        """
        SELECT *
        FROM messages
        WHERE conversation_id=?
          AND user_id=?
        ORDER BY created_at ASC
        """,
        (
            conversation_id,
            user_id
        )
    ).fetchall()

    conn.close()

    output = []

    for row in rows:
        item = dict(row)

        try:
            item["sources"] = json.loads(
                item["sources"] or "[]"
            )
        except Exception:
            item["sources"] = []

        output.append(item)

    return output


def set_plan(
    user_id: str,
    plan: str,
    expires_at: float | None = None
):
    plan = plan.upper()

    if plan not in {
        "FREE",
        "PREMIUM",
        "ULTRA"
    }:
        raise ValueError("Invalid plan.")

    conn = connection()

    conn.execute(
        """
        UPDATE users
        SET plan=?,
            plan_expires=?,
            updated_at=?
        WHERE id=?
        """,
        (
            plan,
            expires_at,
            time.time(),
            user_id
        )
    )

    conn.commit()
    conn.close()


def create_payment(
    user_id: str,
    transaction_id: str,
    plan: str,
    amount: float,
    currency: str,
    status: str
):
    pid = str(uuid.uuid4())

    conn = connection()

    conn.execute(
        """
        INSERT INTO payments
        (
            id,
            user_id,
            transaction_id,
            plan,
            amount,
            currency,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pid,
            user_id,
            transaction_id,
            plan,
            amount,
            currency,
            status,
            time.time()
        )
    )

    conn.commit()
    conn.close()

    return pid


def payment_exists(transaction_id: str):
    conn = connection()

    row = conn.execute(
        """
        SELECT *
        FROM payments
        WHERE transaction_id=?
        """,
        (transaction_id,)
    ).fetchone()

    conn.close()

    return dict(row) if row else None


def create_subscription(
    user_id: str,
    provider_subscription_id: str,
    provider_plan_id: str,
    plan: str,
    status: str,
    expected_amount: int = 0,
    currency: str = "INR",
):
    subscription_id = str(uuid.uuid4())
    now = time.time()
    conn = connection()
    conn.execute(
        """
        INSERT INTO subscriptions (
            id, user_id, provider_subscription_id,
            provider_plan_id, plan, expected_amount, currency,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            subscription_id,
            user_id,
            provider_subscription_id,
            provider_plan_id,
            plan,
            expected_amount,
            currency,
            status,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return subscription_id


def get_subscription(provider_subscription_id: str):
    conn = connection()
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE provider_subscription_id=?",
        (provider_subscription_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_subscription(user_id: str):
    conn = connection()
    row = conn.execute(
        """
        SELECT * FROM subscriptions
        WHERE user_id=?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_subscription(
    provider_subscription_id: str,
    status: str,
    current_end: float | None,
):
    conn = connection()
    conn.execute(
        """
        UPDATE subscriptions
        SET status=?, current_end=?, updated_at=?
        WHERE provider_subscription_id=?
        """,
        (status, current_end, time.time(), provider_subscription_id),
    )
    conn.commit()
    conn.close()


def webhook_event_exists(event_id: str):
    conn = connection()
    row = conn.execute(
        "SELECT 1 FROM payment_webhook_events WHERE event_id=?",
        (event_id,),
    ).fetchone()
    conn.close()
    return row is not None


def record_webhook_event(event_id: str):
    conn = connection()
    conn.execute(
        "INSERT OR IGNORE INTO payment_webhook_events (event_id, created_at) VALUES (?, ?)",
        (event_id, time.time()),
    )
    conn.commit()
    conn.close()


def apply_subscription_webhook(
    event_id: str,
    provider_subscription_id: str,
    status: str,
    current_end: float | None,
    payment: tuple[str, str, int, str] | None = None,
):
    now = time.time()
    conn = connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute(
            "SELECT 1 FROM payment_webhook_events WHERE event_id=?",
            (event_id,),
        ).fetchone():
            conn.rollback()
            return {"duplicate": True}

        subscription = conn.execute(
            """
            SELECT user_id, plan, expected_amount, currency, current_end
            FROM subscriptions
            WHERE provider_subscription_id=?
            """,
            (provider_subscription_id,),
        ).fetchone()
        if not subscription:
            conn.rollback()
            return None

        effective_end = (
            current_end
            if current_end is not None
            else subscription["current_end"]
        )
        conn.execute(
            """
            UPDATE subscriptions
            SET status=?, current_end=?, updated_at=?
            WHERE provider_subscription_id=?
            """,
            (status, effective_end, now, provider_subscription_id),
        )
        conn.execute(
            """
            INSERT INTO payment_webhook_events (event_id, created_at)
            VALUES (?, ?)
            """,
            (event_id, now),
        )

        if payment:
            payment_id, plan, amount, currency = payment
            expected = subscription["expected_amount"]
            expected_currency = subscription["currency"]
            if (
                plan != subscription["plan"]
                or not isinstance(amount, int)
                or isinstance(amount, bool)
                or amount != expected
                or currency != expected_currency
                or not payment_id.startswith("pay_")
            ):
                conn.rollback()
                return {
                    "duplicate": False,
                    "payment_valid": False,
                    "status": status,
                    "plan": "FREE",
                    "plan_expires": None,
                }
            conn.execute(
                """
                INSERT OR IGNORE INTO payments (
                    id, user_id, transaction_id, plan, amount,
                    currency, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'captured', ?)
                """,
                (
                    str(uuid.uuid4()),
                    subscription["user_id"],
                    payment_id,
                    plan,
                    amount / 100,
                    currency,
                    now,
                ),
            )

        entitlement = conn.execute(
            """
            SELECT plan, current_end
            FROM subscriptions
            WHERE user_id=?
              AND status IN ('active', 'cancelled')
              AND current_end > ?
            ORDER BY current_end DESC
            LIMIT 1
            """,
            (subscription["user_id"], now),
        ).fetchone()
        plan, expires_at = (
            (entitlement["plan"], entitlement["current_end"])
            if entitlement
            else ("FREE", None)
        )
        conn.execute(
            """
            UPDATE users
            SET plan=?, plan_expires=?, updated_at=?
            WHERE id=?
            """,
            (plan, expires_at, now, subscription["user_id"]),
        )
        conn.commit()
        return {
            "duplicate": False,
            "status": status,
            "plan": plan,
            "plan_expires": expires_at,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_job(
    user_id: str,
    job_type: str,
    payload: dict
):
    job_id = str(uuid.uuid4())
    now = time.time()

    conn = connection()

    conn.execute(
        """
        INSERT INTO jobs
        (
            id,
            user_id,
            type,
            payload,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 'QUEUED', ?, ?)
        """,
        (
            job_id,
            user_id,
            job_type,
            json.dumps(
                payload,
                ensure_ascii=False
            ),
            now,
            now
        )
    )

    conn.commit()
    conn.close()

    return job_id


def audit(
    action: str,
    user_id: str | None = None,
    metadata=None
):
    aid = str(uuid.uuid4())

    if metadata is None:
        metadata = {}

    conn = connection()

    conn.execute(
        """
        INSERT INTO audit_logs
        (
            id,
            action,
            user_id,
            metadata,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            aid,
            action,
            user_id,
            json.dumps(
                metadata,
                ensure_ascii=False
            ),
            time.time()
        )
    )

    conn.commit()
    conn.close()


def revoke_token_hash(
    token_hash: str,
    expires_at: float
):
    conn = connection()

    conn.execute(
        """
        INSERT OR REPLACE INTO revoked_tokens
        (
            token_hash,
            expires_at
        )
        VALUES (?, ?)
        """,
        (
            token_hash,
            expires_at
        )
    )

    conn.commit()
    conn.close()


def is_token_revoked(token_hash: str):
    conn = connection()

    row = conn.execute(
        """
        SELECT expires_at
        FROM revoked_tokens
        WHERE token_hash=?
        """,
        (token_hash,)
    ).fetchone()

    conn.close()

    if not row:
        return False

    return float(row["expires_at"]) > time.time()


init_db()
