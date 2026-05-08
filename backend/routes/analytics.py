"""
backend/routes/analytics.py
----------------------------
Future prediction, gap analysis, and procurement suggestions.

Routes:
    POST /analytics/predict     — Device requirements for N new joiners
    POST /analytics/gap         — Stock vs requirement gap analysis
    POST /analytics/procurement — Procurement suggestions based on gap
"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from openai  import OpenAI

from backend.models import (
    JoinersRequest,
    SmartPredictionRequest,
    SmartPredictionResponse,
    PredictionResponse,
    GapAnalysisResponse,
    ProcurementResponse,
)
from backend.dependencies import get_db, get_chain, get_current_user
from pipeline.database    import (
    predict_requirements,
    smart_predict_requirements,
    gap_analysis,
    procurement_suggestions,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

GROQ_MODEL = "llama-3.3-70b-versatile"


# ─── LLM reasoning helper ─────────────────────────────────────────────────────

def _usable_stock_count(conn: sqlite3.Connection, device_type: str, min_ram_gb: int = 16) -> int:
    """
    Count IT-Stock items of *device_type* whose RAM is >= min_ram_gb.
    Falls back to 0 on any SQL/cast error (e.g. blank or non-numeric RAM values).
    """
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM inventory
            WHERE  LOWER(current_user) LIKE '%it stock%'
              AND  LOWER(type) = LOWER(?)
              AND  CAST(
                     TRIM(REPLACE(REPLACE(REPLACE(ram,' GB',''),'GB',''),'gb',''))
                   AS INTEGER) >= ?
            """,
            (device_type, min_ram_gb),
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _generate_reasoning(
    client:  OpenAI,
    request: SmartPredictionRequest,
    context: dict,
    conn:    sqlite3.Connection,
) -> tuple[list[dict], list[str], list[str], str, str]:
    """
    1. Compute per-type gap figures entirely from real DB data (no LLM for numbers).
    2. Ask the LLM for analysis bullet-points, actionable recommendations,
       a 3-month outlook sentence, and priority level.

    Returns:
        per_type_gaps   — [{type, required, available, usable_available,
                            shortfall, surplus}, …]
        analysis        — list[str]   (3 concise bullet-point findings)
        recommendations — list[str]   (3-4 actionable bullet points)
        future_outlook  — str         (one-sentence 3-month projection)
        priority        — "High" | "Medium" | "Low"
    """
    stock_map = context.get("stock_by_type", {})
    breakdown = context.get("breakdown", [])

    # ── 1. Compute per-type gaps from real data ────────────────────────────────
    per_type_gaps: list[dict] = []
    total_shortfall = 0

    for row in breakdown:
        t                = row["Type"]
        required         = int(row["Predicted Need"])
        available        = int(stock_map.get(t, 0))
        usable_available = _usable_stock_count(conn, t, min_ram_gb=16)
        shortfall        = max(0, required - available)
        surplus          = max(0, available - required)
        total_shortfall += shortfall

        per_type_gaps.append({
            "type":             t,
            "required":         required,
            "available":        available,
            "usable_available": usable_available,
            "shortfall":        shortfall,
            "surplus":          surplus,
        })

    # ── 2. Derive priority from real numbers (no LLM bias) ────────────────────
    if total_shortfall > 0:
        priority = "High"
    elif any(
        g["available"] > 0 and (g["available"] - g["required"]) < max(1, g["required"] * 0.2)
        for g in per_type_gaps
    ):
        priority = "Medium"
    else:
        priority = "Low"

    # ── 3. Build rich prompt for LLM bullet-point generation ──────────────────
    dept_label = context.get("department", "all departments")
    cats_label = ", ".join(context.get("categories") or ["all device types"])

    gaps_text = "\n".join(
        f"  - {g['type']}: "
        f"need {g['required']} | "
        f"total stock {g['available']} | "
        f"usable (≥16GB) {g['usable_available']} | "
        f"shortfall {g['shortfall']} | "
        f"surplus {g['surplus']}"
        for g in per_type_gaps
    ) or "  (no gap data)"

    os_text = ", ".join(
        f"{r['os']} ({r['cnt']})" for r in context.get("os_breakdown", [])
    ) or "unknown"

    ram_text = ", ".join(
        f"{r['ram']} ({r['cnt']})" for r in context.get("ram_breakdown", [])
    ) or "unknown"

    top_models_text = "\n".join(
        f"  - {r['make']} {r['model']} ({r['cnt']} units)"
        for r in context.get("top_models", [])
    ) or "  (none)"

    prompt = f"""You are a senior IT Asset Manager producing a structured device forecast report.

SCOPE
─────
Department  : {dept_label}
Categories  : {cats_label}
New joiners : {request.new_joiners}

STOCK vs REQUIREMENT GAP  (all numbers are exact — do NOT change them)
────────────────────────────────────────────────────────────────────────
{gaps_text}

EXISTING ENVIRONMENT
────────────────────
OS distribution  : {os_text}
RAM distribution : {ram_text}
Top models in use:
{top_models_text}

────────────────────────────────────────────────────────────────────────
Return ONLY a valid JSON object — no markdown fences, no text outside it.
Use this EXACT structure (each list item is a standalone bullet-point string):

{{
  "analysis": [
    "Finding about stock sufficiency/shortfall with exact numbers from the data above",
    "Finding about spec quality — how many usable (16GB+) vs total available",
    "Finding about model/OS consistency or any compatibility concern"
  ],
  "recommendations": [
    "Actionable step 1 — include quantities and specifics (e.g. 'Upgrade 4 devices from 8GB → 16GB')",
    "Actionable step 2",
    "Actionable step 3",
    "Actionable step 4 (optional — only include if genuinely useful)"
  ],
  "future_outlook": "Single sentence: expected total requirement over next 3 months with a concrete number and brief trend note."
}}

Rules:
• Every analysis/recommendation item must be one self-contained sentence (no sub-bullets).
• Use the exact numbers from the gap table — do not invent figures.
• recommendations must be concrete actions (verbs: Upgrade, Reallocate, Procure, Audit, Migrate).
• Do NOT write paragraphs — every value must be a plain string with no newlines."""

    # ── 4. Call LLM ───────────────────────────────────────────────────────────
    try:
        llm_resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=600,
        )
        raw = llm_resp.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()

        # Robust extraction: find first { … last }
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start : end + 1]

        data            = json.loads(raw)
        analysis        = data.get("analysis", [])
        recommendations = data.get("recommendations", [])
        future_outlook  = str(data.get("future_outlook", ""))

        # Coerce to list[str] in case LLM returns a single string
        if not isinstance(analysis, list):
            analysis = [str(analysis)]
        if not isinstance(recommendations, list):
            recommendations = [str(recommendations)]
        # Drop null / empty items
        analysis        = [s for s in analysis if s and str(s).strip()]
        recommendations = [s for s in recommendations if s and str(s).strip()]

    except Exception as exc:
        # Safe deterministic fallback — use the real numbers we already computed
        analysis = [
            f"{request.new_joiners} device(s) required for incoming joiners.",
            f"Total shortfall across all types: {total_shortfall} unit(s).",
            "Review RAM and OS specs of available stock before assignment.",
        ]
        recommendations = [
            "Check stock items against 16GB RAM requirement before allocation.",
            "Prioritise Windows 11 devices for new joiners.",
            f"(AI detail unavailable: {exc})",
        ]
        future_outlook = (
            f"Based on current hiring rate, expect approximately "
            f"{request.new_joiners * 3} device(s) needed over the next 3 months."
        )

    return per_type_gaps, analysis, recommendations, future_outlook, priority


# ─── Smart prediction (department + category aware) ───────────────────────────

@router.post("/smart-predict", response_model=SmartPredictionResponse)
def smart_predict(
    body:         SmartPredictionRequest,
    conn:         sqlite3.Connection = Depends(get_db),
    chain                            = Depends(get_chain),
    current_user: dict               = Depends(get_current_user),
):
    """
    Predict device requirements for N new joiners filtered by department and
    device category, with AI-generated reasoning and advancement recommendations.
    """
    if body.new_joiners <= 0:
        raise HTTPException(status_code=400, detail="new_joiners must be > 0.")

    breakdown_df, context = smart_predict_requirements(
        conn,
        body.new_joiners,
        body.department,
        body.categories,
    )

    if breakdown_df.empty:
        raise HTTPException(
            status_code=404,
            detail=(
                "Not enough data to generate a prediction for the given filters. "
                "Try a broader department name or remove the category filter."
            ),
        )

    per_type_gaps, analysis, recommendations, future_outlook, priority = (
        _generate_reasoning(chain.client, body, context, conn)
    )

    return SmartPredictionResponse(
        new_joiners     = body.new_joiners,
        department      = body.department or "All Departments",
        categories      = body.categories or ["All"],
        breakdown       = breakdown_df.to_dict(orient="records"),
        per_type_gaps   = per_type_gaps,
        analysis        = analysis,
        recommendations = recommendations,
        future_outlook  = future_outlook,
        priority        = priority,
    )


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