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

def _generate_reasoning(client: OpenAI, request: SmartPredictionRequest, context: dict) -> tuple[str, str]:
    """
    Call the LLM with full context to produce:
      - reasoning   : what is needed and why
      - advancements: recommended upgrades / future improvements

    Returns (reasoning, advancements) as plain text strings.
    """
    dept_label = context.get("department", "all departments")
    cats_label = ", ".join(context.get("categories") or ["all device types"])

    breakdown_text = "\n".join(
        f"  - {row['Type']}: {row['Predicted Need']} unit(s)"
        for row in context.get("breakdown", [])
    ) or "  (no breakdown available)"

    stock_text = "\n".join(
        f"  - {t}: {c} in stock"
        for t, c in context.get("stock_by_type", {}).items()
    ) or "  (no stock data)"

    os_text = ", ".join(
        f"{r['os']} ({r['cnt']})" for r in context.get("os_breakdown", [])
    ) or "unknown"

    ram_text = ", ".join(
        f"{r['ram']} ({r['cnt']})" for r in context.get("ram_breakdown", [])
    ) or "unknown"

    top_models_text = "\n".join(
        f"  - {r['make']} {r['model']} ({r['cnt']} units)"
        for r in context.get("top_models", [])
    ) or "  (no model data)"

    prompt = f"""You are an experienced IT Asset Manager.
The team is onboarding {request.new_joiners} new joiner(s).

SCOPE
-----
Department / Team : {dept_label}
Device categories : {cats_label}

PREDICTED DEVICE NEEDS (based on current assignment ratios)
-----------------------------------------------------------
{breakdown_text}

CURRENT IT STOCK
----------------
{stock_text}

EXISTING ENVIRONMENT (assigned devices in scope)
-------------------------------------------------
OS distribution  : {os_text}
RAM distribution : {ram_text}
Top models in use:
{top_models_text}

─────────────────────────────────────────────────────────────────────
Please respond with ONLY a valid JSON object — no markdown fences,
no explanation outside the JSON. Use this exact structure:

{{
  "reasoning": "2-4 sentence paragraph explaining what devices are needed, any stock gaps, and what to prioritise for the {dept_label} team.",
  "advancements": "2-4 sentence paragraph recommending practical hardware/software upgrades or policy improvements that would benefit this department in the next 1-2 years (e.g. RAM upgrades, OS migration, SSD standardisation, peripheral needs, MDM enhancements)."
}}
─────────────────────────────────────────────────────────────────────"""

    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=600,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip accidental markdown fences if the model adds them
        raw = raw.strip("```json").strip("```").strip()
        data = json.loads(raw)
        return data.get("reasoning", ""), data.get("advancements", "")
    except Exception as exc:
        return (
            f"Prediction calculated successfully. {request.new_joiners} new joiners "
            f"in {dept_label} will need the devices listed above.",
            f"(AI reasoning unavailable: {exc})",
        )


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

    reasoning, advancements = _generate_reasoning(chain.client, body, context)

    return SmartPredictionResponse(
        new_joiners  = body.new_joiners,
        department   = body.department or "All Departments",
        categories   = body.categories or ["All"],
        breakdown    = breakdown_df.to_dict(orient="records"),
        reasoning    = reasoning,
        advancements = advancements,
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