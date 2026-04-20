"""
backend/dependencies.py
-----------------------
Shared FastAPI Depends() providers:
  - get_chain()        → singleton InventoryRAGChain
  - get_db()           → SQLite connection from the chain
  - get_current_user() → decode + validate JWT, return payload
  - require_admin()    → like get_current_user but enforces role == "admin"
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth    import decode_token
from pipeline.chain  import InventoryRAGChain

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH    = os.path.join(BASE_DIR, "master_inventory.csv")
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
DB_PATH     = os.path.join(BASE_DIR, "inventory.db")

bearer_scheme = HTTPBearer(auto_error=True)


# ─── Pipeline singleton ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_chain() -> InventoryRAGChain:
    """Return the singleton RAG chain — built once, reused across all requests."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in .env")
    return InventoryRAGChain(
        api_key=api_key,
        csv_path=CSV_PATH,
        chroma_path=CHROMA_PATH,
        db_path=DB_PATH,
    )


def get_db():
    """Return the SQLite connection from the shared chain."""
    return get_chain().db_conn


# ─── JWT auth ─────────────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Extract and validate the Bearer JWT from the Authorization header.
    Returns the decoded payload dict on success.
    Raises HTTP 401 if missing, invalid, or expired.
    """
    payload = decode_token(credentials.credentials)

    if payload is None or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Like get_current_user but also enforces role == 'admin'.
    Use this for write/destructive operations.
    Raises HTTP 403 if the user is not an admin.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for this action.",
        )
    return current_user
