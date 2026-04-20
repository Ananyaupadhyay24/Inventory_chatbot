"""
pipeline/chain.py
-----------------
Public API — orchestrates the full LangGraph SQL + RAG pipeline.

Architecture
────────────
                       User Query
                           │
                  ┌────────▼─────────┐
                  │   LangGraph      │
                  │   SQL Agent      │
                  └────────┬─────────┘
                           │
            ┌──────────────┼──────────────┐
            │                              │
     "sql" intent                   "semantic" intent
            │                              │
    ┌───────▼────────┐           ┌─────────▼────────┐
    │ GPT generates  │           │  ChromaDB vector  │
    │   SQL query    │           │  similarity search│
    └───────┬────────┘           └─────────┬────────┘
            │                              │
    ┌───────▼────────┐                     │
    │ Execute on     │                     │
    │   SQLite DB    │                     │
    └───────┬────────┘                     │
            │ error?                       │
    ┌───────▼────────┐                     │
    │  GPT fixes SQL │ (up to 3 retries)   │
    │  → retry       │                     │
    └───────┬────────┘                     │
            │ exhausted → ChromaDB ────────┘
            │
   ┌────────▼──────────┐
   │  GPT-4o-mini       │
   │  generates answer  │
   └────────┬──────────┘
            │
      Answer + Result Table
"""

import os
import pandas as pd
from openai import OpenAI

from pipeline.database  import setup_database, get_schema
from pipeline.ingest    import ingest
from pipeline.retriever import SemanticRetriever
from pipeline.sql_agent import build_graph, AgentState


DISPLAY_COLS = [
    "current_user", "old_user", "employee_code", "designation",
    "type", "make", "model", "serial_no", "host_name",
    "ram", "os", "os_build", "storage", "po_number",
    "source_sheet", "agreement_verified",
]


class InventoryRAGChain:
    """
    End-to-end inventory query pipeline.

    Usage:
        chain = InventoryRAGChain(api_key=..., csv_path=..., chroma_path=...)
        answer, df = chain.query("What machine does Anjali Garg have?", history=[])
    """

    def __init__(
        self,
        api_key:      str,
        csv_path:     str,
        chroma_path:  str  = "./chroma_db",
        db_path:      str  = "./inventory.db",
        force_ingest: bool = False,
    ):
        # Groq uses the OpenAI SDK with a different base_url
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        # ── 1. SQLite ──────────────────────────────────────────────────────────
        print("[chain] Setting up SQLite database...")
        self.db_conn = setup_database(csv_path, db_path)
        self.schema  = get_schema(self.db_conn)

        # ── 2. ChromaDB (semantic fallback) ───────────────────────────────────
        self.retriever  = None
        self.collection = None
        try:
            print("[chain] Setting up ChromaDB embeddings (local model)...")
            ingest(csv_path, chroma_path, force=force_ingest)
            self.retriever  = SemanticRetriever(chroma_path)
            self.collection = self.retriever.collection
            print(f"[chain] ChromaDB ready — {self.retriever.count} records indexed.")
        except Exception as exc:
            print(f"[chain] ChromaDB unavailable ({exc}). Semantic fallback disabled.")

        # ── 3. LangGraph SQL agent ─────────────────────────────────────────────
        print("[chain] Compiling LangGraph agent...")
        self.graph = build_graph(
            openai_client=self.client,
            db_conn=self.db_conn,
            schema=self.schema,
            retriever=self.retriever,
        )
        print("[chain] Pipeline ready.\n")

    # ─── Public query interface ───────────────────────────────────────────────

    def query(
        self,
        user_query: str,
        history:    list[dict],
    ) -> tuple[str, pd.DataFrame]:
        """
        Run the full LangGraph pipeline on a natural language query.

        Args:
            user_query : The user's question.
            history    : Conversation history for multi-turn support.

        Returns:
            (answer_text, result_dataframe)
        """
        initial_state: AgentState = {
            "query":         user_query,
            "query_type":    "",
            "sql_query":     "",
            "sql_result":    "",
            "sql_error":     "",
            "retry_count":   0,
            "semantic_docs": [],
            "final_answer":  "",
            "result_df":     [],
            "history":       history,
        }

        final_state = self.graph.invoke(initial_state)
        answer      = final_state.get("final_answer", "No answer generated.")

        # ── Build display DataFrame ──
        result_df = pd.DataFrame()

        records = final_state.get("result_df", [])
        if records:
            df   = pd.DataFrame(records)
            cols = [c for c in DISPLAY_COLS if c in df.columns]
            result_df = df[cols].reset_index(drop=True) if cols else df.reset_index(drop=True)

        elif final_state.get("semantic_docs"):
            df   = pd.DataFrame(final_state["semantic_docs"])
            df   = df.drop(columns=["_text", "_similarity", "_distance"], errors="ignore")
            cols = [c for c in DISPLAY_COLS if c in df.columns]
            result_df = df[cols].reset_index(drop=True) if cols else df.reset_index(drop=True)

        return answer, result_df
