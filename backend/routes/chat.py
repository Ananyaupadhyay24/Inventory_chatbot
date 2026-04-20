"""
backend/routes/chat.py
----------------------
POST /chat  — Natural language query via LangGraph SQL agent.
"""

from fastapi import APIRouter, Depends, HTTPException

from backend.models       import ChatRequest, ChatResponse
from backend.dependencies import get_chain, get_current_user
from pipeline.chain       import InventoryRAGChain

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
def chat(
    body:         ChatRequest,
    chain:        InventoryRAGChain = Depends(get_chain),
    current_user: dict              = Depends(get_current_user),   # ← JWT required
):
    """
    Send a natural language query to the LangGraph SQL agent.

    Request body:
        query   : The user's question.
        history : Previous conversation turns (role + content).

    Returns:
        answer  : Natural language answer from GPT-4o-mini.
        records : Matching inventory records (list of dicts).
        count   : Number of records returned.
    """
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    history = [m.model_dump() for m in body.history]

    try:
        answer, result_df = chain.query(
            user_query=body.query,
            history=history,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    records = result_df.to_dict(orient="records") if not result_df.empty else []

    return ChatResponse(
        answer=answer,
        records=records,
        count=len(records),
    )
