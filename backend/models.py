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
    new_joiners:  int
    department:   str
    categories:   list[str]
    breakdown:    list[dict]
    reasoning:    str        # LLM: what you need and why
    advancements: str        # LLM: recommended future improvements


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