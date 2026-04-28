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
# FIX: replaced lru_cache with an explicit singleton pattern.
# lru_cache does NOT cache exceptions — if get_chain() raises on the first call
# (e.g. missing CSV), every subsequent request retries the full expensive setup.
# This manual pattern caches the instance on success and re-raises clearly on failure.

_chain_instance: InventoryRAGChain | None = None
_chain_error:    Exception | None          = None


def get_chain() -> InventoryRAGChain:
    """
    Return the singleton RAG chain — built once, reused across all requests.
    Raises RuntimeError with a clear message if the chain failed to initialise.
    """
    global _chain_instance, _chain_error

    if _chain_instance is not None:
        return _chain_instance

    if _chain_error is not None:
        raise RuntimeError(
            f"Pipeline failed to initialise and will not retry: {_chain_error}"
        ) from _chain_error

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in .env")

    try:
        _chain_instance = InventoryRAGChain(
            api_key=api_key,
            csv_path=CSV_PATH,
            chroma_path=CHROMA_PATH,
            db_path=DB_PATH,
        )
        return _chain_instance
    except Exception as exc:
        _chain_error = exc
        raise


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