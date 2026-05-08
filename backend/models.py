"""
backend/models.py
-----------------
Pydantic request and response models for the FastAPI backend.
"""

from typing import Optional
from pydantic import BaseModel


# ─── Shared ───────────────────────────────────────────────────────────────────

class MessageItem(BaseModel):
    role:    str   # "user" | "assistant"
    content: str


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query:   str
    history: list[MessageItem] = []


class ChatResponse(BaseModel):
    answer:  str
    records: list[dict] = []
    count:   int        = 0


# ─── Asset Release ────────────────────────────────────────────────────────────

class ReleasePreviewRequest(BaseModel):
    identifier: str            # employee name or code


class ReleaseConfirmRequest(BaseModel):
    identifier:   str
    new_location: str = "IT Stock"


class ReleaseResponse(BaseModel):
    released_count: int
    devices:        list[dict] = []
    message:        str


# ─── Analytics ────────────────────────────────────────────────────────────────

class JoinersRequest(BaseModel):
    new_joiners: int


class SmartPredictionRequest(BaseModel):
    new_joiners: int
    department:  str       = ""   # e.g. "Engineering", "Design", "QA"
    categories:  list[str] = []   # e.g. ["Laptop", "Desktop"]


class StockSummaryResponse(BaseModel):
    records: list[dict]
    total:   int


class SmartPredictionResponse(BaseModel):
    new_joiners:     int
    department:      str
    categories:      list[str]
    breakdown:       list[dict]

    # ── Computed from real data (no LLM) ──────────────────────────────
    # Each entry: {type, required, available, usable_available, shortfall, surplus}
    per_type_gaps:   list[dict]

    # ── LLM-generated structured output ───────────────────────────────
    analysis:        list[str]   # 3 bullet points: env/stock findings
    recommendations: list[str]   # 3-4 actionable bullet points
    future_outlook:  str         # 1-sentence 3-month projection
    priority:        str         # "High" | "Medium" | "Low"


class PredictionResponse(BaseModel):
    new_joiners: int
    breakdown:   list[dict]


class GapAnalysisResponse(BaseModel):
    new_joiners: int
    breakdown:   list[dict]
    has_shortage: bool
    shortage_types: list[str]


class ProcurementResponse(BaseModel):
    new_joiners:  int
    suggestions:  list[dict]
    total_units:  int
    sufficient:   bool


# ─── Dashboard stats ──────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total:           int
    laptops:         int
    desktops:        int
    mac_mini:        int
    in_stock:        int
    faulty:          int
    windows_10:      int
    windows_11:      int
    linux:           int
    macos:           int
    missing_serial:  int
    missing_agreement: int