"""
pipeline/sql_agent.py
---------------------
LangGraph-based SQL agent for natural language → SQL → answer.
Uses Groq (llama-3.3-70b-versatile) via OpenAI-compatible API — free tier.

Agent Graph
───────────
  START
    │
    ▼
  classify ──── "semantic" ──────────────────────────┐
    │                                                 │
    │ "sql"                                           │
    ▼                                                 │
  generate_sql                                        │
    │                                                 │
    ▼                                                 │
  execute_sql ─── success ───────────────────────┐   │
    │                                             │   │
    │ error (retry_count < 3)                     │   │
    ▼                                             │   │
  fix_sql ──────────────────────► execute_sql     │   │
    │                                             │   │
    │ exhausted (retry_count >= 3)                │   │
    ▼                                             │   │
  semantic_search ◄────────────────────────────────   │
    │               ◄────────────────────────────────-┘
    ▼
  generate_answer
    │
    ▼
   END
"""

import sqlite3
from typing import TypedDict, Literal

import pandas as pd
from openai import OpenAI
from langgraph.graph import StateGraph, END


GROQ_MODEL = "llama-3.3-70b-versatile"


# ─── Agent State ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    query:          str
    query_type:     str
    sql_query:      str
    sql_result:     str
    sql_error:      str
    retry_count:    int
    semantic_docs:  list[dict]
    final_answer:   str
    result_df:      list[dict]
    history:        list[dict]


# ─── Prompts ──────────────────────────────────────────────────────────────────

_CLASSIFIER_PROMPT = """Classify this IT inventory query into exactly one category:

  sql      → needs specific data: lookup, filter, count, list, aggregation
  semantic → vague, conceptual, or requires reasoning / recommendation

Reply with ONLY the word: sql   OR   semantic"""


def _sql_gen_prompt(schema: str) -> str:
    return f"""You are an expert SQLite query writer for an IT asset inventory.

DATABASE SCHEMA
{schema}

WRITING RULES
─────────────
• Table name  : inventory
• Use LOWER() and LIKE '%..%' for all text matching (case-insensitive)
• IT Stock    : LOWER(current_user) LIKE '%it stock%'
• Faulty      : LOWER(current_user) LIKE '%fault%' OR LOWER(source_sheet) LIKE '%fault%'
• Missing agreement (laptops): agreement_verified = '' AND agreement_doc = ''
                                AND LOWER(type) = 'laptop'
• RAM numeric compare : CAST(REPLACE(REPLACE(ram,' GB',''),' gb','') AS INTEGER)
• OS upgrade targets  : LOWER(os) LIKE '%windows 10%'
• OS build filter     : UPPER(os_build) = '22H2'  (exact match after UPPER)
• Duplicate serials   : GROUP BY serial_no HAVING COUNT(*) > 1
• Always SELECT meaningful columns — avoid SELECT *
• Add ORDER BY for readability where helpful
• Add LIMIT 100 unless the user asks for a count / summary

OUTPUT: Return ONLY the SQL query. No markdown fences, no explanation."""


_SQL_FIX_PROMPT = """A SQLite query failed. Rewrite it to fix the error.

Rules:
• Table: inventory  |  SQLite syntax only
• LOWER() + LIKE for string matching
• CAST(REPLACE(REPLACE(ram,' GB',''),' gb','') AS INTEGER) for RAM
• Return ONLY the corrected SQL — nothing else."""


_ANSWER_PROMPT = """You are a concise, professional IT Admin assistant.

Answer the user's question using the inventory data provided.
• Be specific: include names, counts, serial numbers where relevant.
• Keep it to 2–4 sentences.
• If the result is empty, say no records found and suggest a refinement.
• Do NOT reproduce the full data table."""


# ─── Node factory ─────────────────────────────────────────────────────────────

def make_nodes(
    openai_client: OpenAI,
    db_conn:       sqlite3.Connection,
    schema:        str,
    retriever,
):
    def _llm(system: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 400) -> str:
        resp = openai_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    # ── 1. Classify ──────────────────────────────────────────────────────────
    def classify_node(state: AgentState) -> AgentState:
        raw   = _llm(_CLASSIFIER_PROMPT, [{"role": "user", "content": state["query"]}], max_tokens=5).lower()
        qtype = raw if raw in ("sql", "semantic") else "sql"
        return {**state, "query_type": qtype}

    # ── 2. Generate SQL ───────────────────────────────────────────────────────
    def generate_sql_node(state: AgentState) -> AgentState:
        messages = [
            msg for msg in state["history"][-4:]
            if msg.get("role") in ("user", "assistant")
        ]
        messages.append({"role": "user", "content": state["query"]})

        sql = _llm(_sql_gen_prompt(schema), messages).strip().strip("`").strip()
        if sql.lower().startswith("sql\n"):
            sql = sql[4:].strip()
        return {**state, "sql_query": sql, "sql_error": ""}

    # ── 3. Execute SQL ────────────────────────────────────────────────────────
    def execute_sql_node(state: AgentState) -> AgentState:
        try:
            df         = pd.read_sql_query(state["sql_query"], db_conn)
            result_str = (
                f"{len(df)} row(s) returned.\n"
                f"{df.head(20).to_string(index=False)}"
            ) if not df.empty else "Query returned 0 rows."
            return {
                **state,
                "sql_result": result_str,
                "sql_error":  "",
                "result_df":  df.astype(str).to_dict(orient="records"),
            }
        except Exception as exc:
            return {
                **state,
                "sql_result":  "",
                "sql_error":   str(exc),
                "retry_count": state.get("retry_count", 0) + 1,
                "result_df":   [],
            }

    # ── 4. Fix SQL ────────────────────────────────────────────────────────────
    def fix_sql_node(state: AgentState) -> AgentState:
        user_content = (
            f"Question : {state['query']}\n"
            f"Failed SQL:\n{state['sql_query']}\n"
            f"Error     : {state['sql_error']}"
        )
        fixed = _llm(_SQL_FIX_PROMPT, [{"role": "user", "content": user_content}]).strip().strip("`").strip()
        if fixed.lower().startswith("sql\n"):
            fixed = fixed[4:].strip()
        return {**state, "sql_query": fixed}

    # ── 5. Semantic search (fallback) ─────────────────────────────────────────
    def semantic_search_node(state: AgentState) -> AgentState:
        if retriever is None:
            return {**state, "semantic_docs": []}
        docs = retriever.search(state["query"], n_results=12)
        return {**state, "semantic_docs": docs}

    # ── 6. Generate natural language answer ───────────────────────────────────
    def generate_answer_node(state: AgentState) -> AgentState:
        if state.get("sql_result"):
            context = f"[SQL Result]\n{state['sql_result']}"
        elif state.get("semantic_docs"):
            lines   = [d.get("_text", str(d)) for d in state["semantic_docs"][:10]]
            context = "[Semantic Search Results]\n" + "\n".join(lines)
        else:
            context = "No matching data found."

        messages = [
            msg for msg in state["history"][-4:]
            if msg.get("role") in ("user", "assistant")
        ]
        messages.append({
            "role": "user",
            "content": f"Question: {state['query']}\n\nData:\n{context}",
        })
        answer = _llm(_ANSWER_PROMPT, messages, temperature=0.2, max_tokens=300)
        return {**state, "final_answer": answer}

    return (
        classify_node,
        generate_sql_node,
        execute_sql_node,
        fix_sql_node,
        semantic_search_node,
        generate_answer_node,
    )


# ─── Routing conditions ───────────────────────────────────────────────────────

def _route_classify(state: AgentState) -> Literal["sql", "semantic"]:
    return "sql" if state.get("query_type") == "sql" else "semantic"


def _route_execute(state: AgentState) -> Literal["success", "retry", "exhausted"]:
    if not state.get("sql_error"):
        return "success"
    return "retry" if state.get("retry_count", 0) < 3 else "exhausted"


# ─── Graph builder ────────────────────────────────────────────────────────────

def build_graph(
    openai_client: OpenAI,
    db_conn:       sqlite3.Connection,
    schema:        str,
    retriever,
):
    (
        classify_node,
        generate_sql_node,
        execute_sql_node,
        fix_sql_node,
        semantic_search_node,
        generate_answer_node,
    ) = make_nodes(openai_client, db_conn, schema, retriever)

    g = StateGraph(AgentState)
    g.add_node("classify",        classify_node)
    g.add_node("generate_sql",    generate_sql_node)
    g.add_node("execute_sql",     execute_sql_node)
    g.add_node("fix_sql",         fix_sql_node)
    g.add_node("semantic_search", semantic_search_node)
    g.add_node("generate_answer", generate_answer_node)

    g.set_entry_point("classify")
    g.add_conditional_edges(
        "classify",
        _route_classify,
        {"sql": "generate_sql", "semantic": "semantic_search"},
    )
    g.add_edge("generate_sql", "execute_sql")
    g.add_conditional_edges(
        "execute_sql",
        _route_execute,
        {"success": "generate_answer", "retry": "fix_sql", "exhausted": "semantic_search"},
    )
    g.add_edge("fix_sql",         "execute_sql")
    g.add_edge("semantic_search", "generate_answer")
    g.add_edge("generate_answer", END)

    return g.compile()
