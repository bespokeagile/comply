"""Funded scans: invite-only credit system for server-funded semantic scans.

Admin grants credits to specific emails via invite tokens.
Invited users can run semantic scans without providing their own API key.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

_DB_DIR = os.path.expanduser("~/.comply")
_DB_PATH = os.path.join(_DB_DIR, "scans.db")
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection (reuses same DB as store.py)."""
    conn = getattr(_local, "funded_conn", None)
    if conn is None:
        os.makedirs(_DB_DIR, exist_ok=True)
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.funded_conn = conn
        _ensure_funded_schema(conn)
    return conn


def _ensure_funded_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS funded_credits (
            email           TEXT PRIMARY KEY,
            invite_token    TEXT UNIQUE NOT NULL,
            total_credits   INTEGER NOT NULL DEFAULT 5,
            used_credits    INTEGER NOT NULL DEFAULT 0,
            granted_by      TEXT NOT NULL DEFAULT 'admin',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS funded_usage (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT NOT NULL,
            scan_id         TEXT NOT NULL,
            framework       TEXT NOT NULL DEFAULT '',
            model           TEXT NOT NULL DEFAULT '',
            input_tokens    INTEGER NOT NULL DEFAULT 0,
            output_tokens   INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_funded_usage_email
            ON funded_usage (email, created_at DESC);

        CREATE TABLE IF NOT EXISTS funded_daily_cap (
            date            TEXT PRIMARY KEY,
            scan_count      INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0
        );
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def is_funded_enabled() -> bool:
    """Check if funded scans are enabled."""
    return os.environ.get("COMPLY_FUNDED_SCANS", "").lower() in ("true", "1", "yes")


def get_funded_api_key() -> Optional[str]:
    """Return the dedicated API key for funded scans."""
    return os.environ.get("COMPLY_FUNDED_API_KEY") or None


def get_funded_model() -> str:
    """Return the model to use for funded scans."""
    return os.environ.get("COMPLY_FUNDED_MODEL", "claude-sonnet-4-5-20250514")


def get_admin_token() -> Optional[str]:
    """Return the admin auth token for funded scan management."""
    return os.environ.get("COMPLY_FUNDED_ADMIN_TOKEN") or None


def get_daily_cap() -> int:
    return int(os.environ.get("COMPLY_FUNDED_DAILY_CAP", "20"))


def get_monthly_cap() -> int:
    return int(os.environ.get("COMPLY_FUNDED_MONTHLY_CAP", "200"))


def get_max_files() -> int:
    """Max files for funded scans (cost control)."""
    return int(os.environ.get("COMPLY_FUNDED_MAX_FILES", "200"))


# ---------------------------------------------------------------------------
# Credit management
# ---------------------------------------------------------------------------

def grant_credits(email: str, credits: int = 5, granted_by: str = "admin") -> dict:
    """Grant funded scan credits to an email. Creates invite token."""
    conn = _get_conn()
    now = _now()

    # Check if already exists
    row = conn.execute(
        "SELECT * FROM funded_credits WHERE email = ?", (email,)
    ).fetchone()

    if row:
        # Update existing: add credits
        new_total = row["total_credits"] + credits
        conn.execute(
            "UPDATE funded_credits SET total_credits = ?, granted_by = ?, updated_at = ? WHERE email = ?",
            (new_total, granted_by, now, email),
        )
        conn.commit()
        token = row["invite_token"]
        return {
            "email": email,
            "invite_token": token,
            "total_credits": new_total,
            "used_credits": row["used_credits"],
            "remaining": new_total - row["used_credits"],
        }

    # Create new
    token = secrets.token_urlsafe(16)
    conn.execute(
        """INSERT INTO funded_credits (email, invite_token, total_credits, used_credits, granted_by, created_at, updated_at)
           VALUES (?, ?, ?, 0, ?, ?, ?)""",
        (email, token, credits, granted_by, now, now),
    )
    conn.commit()
    return {
        "email": email,
        "invite_token": token,
        "total_credits": credits,
        "used_credits": 0,
        "remaining": credits,
    }


def revoke_credits(email: str, reduce_by: Optional[int] = None) -> Optional[dict]:
    """Revoke or reduce credits for an email. Returns None if not found."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM funded_credits WHERE email = ?", (email,)
    ).fetchone()
    if row is None:
        return None

    now = _now()
    if reduce_by is None:
        # Full revoke: set total = used (no remaining)
        conn.execute(
            "UPDATE funded_credits SET total_credits = used_credits, updated_at = ? WHERE email = ?",
            (now, email),
        )
    else:
        new_total = max(row["used_credits"], row["total_credits"] - reduce_by)
        conn.execute(
            "UPDATE funded_credits SET total_credits = ?, updated_at = ? WHERE email = ?",
            (new_total, now, email),
        )

    conn.commit()
    updated = conn.execute(
        "SELECT * FROM funded_credits WHERE email = ?", (email,)
    ).fetchone()
    return _credit_to_dict(updated)


def check_token(token: str) -> Optional[dict]:
    """Check an invite token. Returns credit info or None if invalid."""
    if not token:
        return None
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM funded_credits WHERE invite_token = ?", (token,)
    ).fetchone()
    if row is None:
        return None
    return _credit_to_dict(row)


def has_credits(token: str) -> bool:
    """Check if token has remaining credits and global caps aren't exceeded."""
    info = check_token(token)
    if info is None:
        return False
    if info["remaining"] <= 0:
        return False
    # Check daily cap
    if _daily_count() >= get_daily_cap():
        return False
    return True


def use_credit(token: str, scan_id: str, framework: str = "",
               model: str = "", input_tokens: int = 0,
               output_tokens: int = 0, estimated_cost: float = 0) -> bool:
    """Consume one credit for a funded scan. Returns False if no credits left."""
    conn = _get_conn()
    now = _now()
    today = _today()

    row = conn.execute(
        "SELECT * FROM funded_credits WHERE invite_token = ?", (token,)
    ).fetchone()
    if row is None:
        return False

    remaining = row["total_credits"] - row["used_credits"]
    if remaining <= 0:
        return False

    # Check daily cap
    if _daily_count() >= get_daily_cap():
        return False

    # Consume credit
    conn.execute(
        "UPDATE funded_credits SET used_credits = used_credits + 1, updated_at = ? WHERE invite_token = ?",
        (now, token),
    )

    # Log usage
    conn.execute(
        """INSERT INTO funded_usage (email, scan_id, framework, model, input_tokens, output_tokens, estimated_cost_usd, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (row["email"], scan_id, framework, model, input_tokens, output_tokens, estimated_cost, now),
    )

    # Update daily cap
    conn.execute(
        """INSERT INTO funded_daily_cap (date, scan_count, estimated_cost_usd)
           VALUES (?, 1, ?)
           ON CONFLICT(date) DO UPDATE SET
               scan_count = scan_count + 1,
               estimated_cost_usd = estimated_cost_usd + excluded.estimated_cost_usd""",
        (today, estimated_cost),
    )

    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Admin queries
# ---------------------------------------------------------------------------

def list_users() -> list:
    """List all invited users with their credit info."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM funded_credits ORDER BY created_at DESC"
    ).fetchall()
    return [_credit_to_dict(r) for r in rows]


def get_usage_stats() -> dict:
    """Return aggregate usage statistics."""
    conn = _get_conn()
    today = _today()

    # Today's usage
    day_row = conn.execute(
        "SELECT scan_count, estimated_cost_usd FROM funded_daily_cap WHERE date = ?",
        (today,)
    ).fetchone()
    today_scans = day_row["scan_count"] if day_row else 0
    today_cost = day_row["estimated_cost_usd"] if day_row else 0

    # This month
    month_prefix = today[:7]  # YYYY-MM
    month_row = conn.execute(
        """SELECT SUM(scan_count) as scans, SUM(estimated_cost_usd) as cost
           FROM funded_daily_cap WHERE date LIKE ?""",
        (month_prefix + "%",)
    ).fetchone()
    month_scans = (month_row["scans"] or 0) if month_row else 0
    month_cost = (month_row["cost"] or 0) if month_row else 0

    # Total all time
    total_row = conn.execute(
        "SELECT COUNT(*) as total, SUM(estimated_cost_usd) as cost FROM funded_usage"
    ).fetchone()
    total_scans = (total_row["total"] or 0) if total_row else 0
    total_cost = (total_row["cost"] or 0) if total_row else 0

    # User count
    user_count = conn.execute("SELECT COUNT(*) as c FROM funded_credits").fetchone()["c"]

    return {
        "today": {"scans": today_scans, "cost": round(today_cost, 4), "cap": get_daily_cap()},
        "month": {"scans": month_scans, "cost": round(month_cost, 4), "cap": get_monthly_cap()},
        "total": {"scans": total_scans, "cost": round(total_cost, 4)},
        "invited_users": user_count,
        "enabled": is_funded_enabled(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _daily_count() -> int:
    """Return today's funded scan count."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT scan_count FROM funded_daily_cap WHERE date = ?",
        (_today(),)
    ).fetchone()
    return row["scan_count"] if row else 0


def _credit_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["remaining"] = d["total_credits"] - d["used_credits"]
    return d
