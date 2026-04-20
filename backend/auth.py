"""
backend/auth.py
---------------
JWT utilities and user management.

Users are stored in the inventory SQLite database (users table).
Passwords are bcrypt-hashed.

Default users created on first startup:
    username: admin   password: admin123   role: admin
    username: viewer  password: viewer123  role: viewer
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from jose       import JWTError, jwt
from passlib.context import CryptContext

# ─── Config ───────────────────────────────────────────────────────────────────

SECRET_KEY                   = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM                    = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES  = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS    = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS",   "7"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Password helpers ────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── Token helpers ────────────────────────────────────────────────────────────

def create_access_token(username: str, role: str) -> str:
    expire  = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "type": "access", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(username: str, role: str) -> str:
    expire  = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": username, "role": role, "type": "refresh", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT. Returns payload dict or None on failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ─── User management (SQLite) ─────────────────────────────────────────────────

def init_users_table(conn: sqlite3.Connection) -> None:
    """Create users table and seed default users if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()

    # Seed defaults only if table is empty
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        defaults = [
            ("admin",  hash_password("admin123"),  "admin"),
            ("viewer", hash_password("viewer123"), "viewer"),
        ]
        conn.executemany(
            "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
            defaults,
        )
        conn.commit()
        print("[auth] Default users created: admin / viewer")


def get_user(conn: sqlite3.Connection, username: str) -> dict | None:
    """Fetch a user record by username."""
    row = conn.execute(
        "SELECT username, hashed_password, role, is_active FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None:
        return None
    return {"username": row[0], "hashed_password": row[1], "role": row[2], "is_active": row[3]}


def authenticate_user(conn: sqlite3.Connection, username: str, password: str) -> dict | None:
    """
    Verify credentials.
    Returns the user dict on success, None on failure.
    """
    user = get_user(conn, username)
    if user is None:
        return None
    if not user["is_active"]:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user
