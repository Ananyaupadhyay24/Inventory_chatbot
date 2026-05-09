"""
backend/main.py
---------------
FastAPI application entry point.

Run with:
    uvicorn backend.main:app --reload --port 8000

Interactive docs (with JWT support):
    http://localhost:8000/docs
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env explicitly before any other imports so all modules see the vars
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.auth         import init_users_table
from backend.dependencies import get_chain, get_db
from backend.routes       import chat, assets, analytics
from backend.routes       import auth_router


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Initialising IT Inventory pipeline...")
    try:
        chain = get_chain()
        init_users_table(chain.db_conn)  # create users table + seed defaults
        print("[startup] Pipeline ready. Users table initialised.")
    except Exception as exc:
        print(f"[startup] WARNING: {exc}")
    yield
    print("[shutdown] Goodbye.")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="IT Inventory Assistant — API",
    description=(
        "REST API for IT Asset Management. "
        "All endpoints (except /auth/login) require a Bearer JWT.\n\n"
        "**Default credentials:**\n"
        "- admin / admin123  (full access)\n"
        "- viewer / viewer123 (read-only)\n\n"
        "Click **Authorize** above and paste your token as: `Bearer <token>`"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",      # ← add this
        "http://127.0.0.1:3000",      # ← add this
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(auth_router.router)   # /auth/*  — public
app.include_router(chat.router)          # /chat    — JWT required
app.include_router(assets.router)        # /assets/* — JWT required
app.include_router(analytics.router)     # /analytics/* — JWT required


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
def health():
    chain = get_chain()
    return {
        "status":         "ok",
        "db":             os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), "inventory.db")),
        "chroma_indexed": chain.collection.count() if chain.collection else 0,
    }
