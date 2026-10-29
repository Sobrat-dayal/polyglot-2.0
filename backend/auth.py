"""Small server-side session layer for the local Stage 2 deployment.

It intentionally keeps guest translation available while providing hashed
passwords and signed, HttpOnly sessions for project/workspace access.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

SESSION_SECRET = os.getenv("POLYGLOT_SESSION_SECRET", "development-only-change-me").encode()
SESSION_DAYS = 14


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310_000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def make_session_token(session_id: str) -> str:
    signature = hmac.new(SESSION_SECRET, session_id.encode(), hashlib.sha256).hexdigest()
    return f"{session_id}.{signature}"


def read_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    session_id, signature = token.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET, session_id.encode(), hashlib.sha256).hexdigest()
    return session_id if hmac.compare_digest(signature, expected) else None


def create_session(connection: sqlite3.Connection, user_id: str) -> str:
    session_id = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    connection.execute("INSERT INTO sessions(id,user_id,expires_at) VALUES(?,?,?)", (session_id, user_id, expires))
    return make_session_token(session_id)


def current_user(connection: sqlite3.Connection, token: str | None) -> str:
    session_id = read_session(token)
    if not session_id:
        return "guest"
    row = connection.execute(
        "SELECT user_id FROM sessions WHERE id = ? AND expires_at > ?",
        (session_id, datetime.now(timezone.utc).isoformat()),
    ).fetchone()
    return row[0] if row else "guest"


def password_hash(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    return _hash_password(password)
