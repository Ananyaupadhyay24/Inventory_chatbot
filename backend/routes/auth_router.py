"""
backend/routes/auth_router.py
------------------------------
Authentication endpoints.

POST /auth/login    — returns access_token + refresh_token
POST /auth/refresh  — returns new access_token using a valid refresh_token
GET  /auth/me       — returns current user info
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.auth         import authenticate_user, create_access_token, create_refresh_token, decode_token
from backend.dependencies import get_current_user, get_db

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─── Request / Response models ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    role:          str

class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Authenticate with username + password.
    Returns a short-lived access token (30 min) and a long-lived refresh token (7 days).
    """
    user = authenticate_user(conn, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token  = create_access_token(user["username"], user["role"]),
        refresh_token = create_refresh_token(user["username"], user["role"]),
        role          = user["role"],
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest):
    """
    Exchange a valid refresh token for a new access token.
    Does NOT require the Authorization header — only the refresh token in the body.
    """
    payload = decode_token(body.refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    username = payload["sub"]
    role     = payload.get("role", "viewer")

    return TokenResponse(
        access_token  = create_access_token(username, role),
        refresh_token = create_refresh_token(username, role),   # rotate
        role          = role,
    )


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    return {
        "username": current_user["sub"],
        "role":     current_user.get("role", "viewer"),
    }
