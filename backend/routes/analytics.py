"""
backend/routes/analytics.py
----------------------------
Future prediction, gap analysis, and procurement suggestions.

Routes:
    POST /analytics/predict     — Device requirements for N new joiners
    POST /analytics/gap         — Stock vs requirement gap analysis
    POST /analytics/procurement — Procurement suggestions based on gap
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.models import (
    JoinersRequest,
    PredictionResponse,
    GapAnalysisResponse,
    ProcurementResponse,
)
from backend.dependencies import get_db, get_current_user
from pipeline.database    import (
    predict_requirements,
    gap_analysis,
    procurement_suggestions,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ─── Future requirement prediction ───────────────────────────────────────────

@router.post("/predict", response_model=PredictionResponse)
def predict(
    body:         JoinersRequest,
    conn:         sqlite3.Connection = Depends(get_db),
    current_user: dict               = Depends(get_current_user),
):
    """
    Predict how many devices are needed for N new joiners
    based on current device-to-employee ratios.
    """
    if body.new_joiners <= 0:
        raise HTTPException(status_code=400, detail="new_joiners must be > 0.")

    df = predict_requirements(conn, body.new_joiners)
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail="Not enough assigned records to calculate a prediction.",
        )

    return PredictionResponse(
        new_joiners=body.new_joiners,
        breakdown=df.to_dict(orient="records"),
    )


# ─── Gap analysis ─────────────────────────────────────────────────────────────

@router.post("/gap", response_model=GapAnalysisResponse)
def gap(
    body:         JoinersRequest,
    conn:         sqlite3.Connection = Depends(get_db),
    current_user: dict               = Depends(get_current_user),
):
    """
    Compare current IT Stock against predicted device requirements.
    Returns per-type breakdown with shortage/sufficient status.
    """
    if body.new_joiners <= 0:
        raise HTTPException(status_code=400, detail="new_joiners must be > 0.")

    df = gap_analysis(conn, body.new_joiners)
    if df.empty:
        raise HTTPException(status_code=404, detail="Could not compute gap analysis.")

    shortage_rows  = df[df["Gap"] < 0]
    shortage_types = shortage_rows["Type"].tolist() if not shortage_rows.empty else []

    return GapAnalysisResponse(
        new_joiners=body.new_joiners,
        breakdown=df.to_dict(orient="records"),
        has_shortage=len(shortage_types) > 0,
        shortage_types=shortage_types,
    )


# ─── Procurement suggestions ──────────────────────────────────────────────────

@router.post("/procurement", response_model=ProcurementResponse)
def procurement(
    body:         JoinersRequest,
    conn:         sqlite3.Connection = Depends(get_db),
    current_user: dict               = Depends(get_current_user),
):
    """
    Generate a procurement list: recommended models and quantities
    based on gap analysis for N new joiners.
    """
    if body.new_joiners <= 0:
        raise HTTPException(status_code=400, detail="new_joiners must be > 0.")

    df = procurement_suggestions(conn, body.new_joiners)

    if "Message" in df.columns:
        return ProcurementResponse(
            new_joiners=body.new_joiners,
            suggestions=[],
            total_units=0,
            sufficient=True,
        )

    total = int(df["Qty to Procure"].sum()) if not df.empty and "Qty to Procure" in df.columns else 0

    return ProcurementResponse(
        new_joiners=body.new_joiners,
        suggestions=df.to_dict(orient="records"),
        total_units=total,
        sufficient=df.empty,
    )
