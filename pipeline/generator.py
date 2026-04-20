"""
pipeline/generator.py
---------------------
LLM response generation layer.

Two responsibilities:
  1. classify()       — Determine which retrieval mode to use for a query.
  2. generate()       — Generate a natural language answer from retrieved context.
  3. build_pandas_code() — For filter/aggregate queries, produce safe pandas code.
"""

import pandas as pd
from openai import OpenAI

GROQ_MODEL = "llama-3.3-70b-versatile"


# ─── Query types ──────────────────────────────────────────────────────────────
QUERY_TYPES = {
    "lookup":    "Find details for a specific person, serial number, or host.",
    "filter":    "List all records matching certain criteria (OS, RAM, type, make).",
    "aggregate": "Count, summarize, or compare data across records.",
    "semantic":  "Vague, general, or conversational question needing reasoning.",
}

# ─── Prompts ──────────────────────────────────────────────────────────────────

CLASSIFIER_PROMPT = f"""You are an IT inventory query classifier.
Classify the user's query into exactly one of these categories:

{chr(10).join(f"- {k}: {v}" for k, v in QUERY_TYPES.items())}

Respond with ONLY the category name. No explanation."""


PANDAS_CODE_PROMPT = """You are an IT inventory data analyst.
You have a pandas DataFrame called `df` with these columns (all strings, '' for missing):

  current_user     — employee name / "IT Stock [location]" if unassigned
  old_user         — previous user name
  employee_code    — e.g. NTZ2186, C1034
  designation      — job title
  type             — "Laptop" | "Desktop" | "MAC Mini"
  make             — "Lenovo" | "Dell" | "Apple"
  model            — E14, L14, M720t, V520, V14, Neo 50, L480, E14 G6 …
  serial_no        — device serial number
  host_name        — e.g. NTZ-LAP-045, NTZ-CPU-101
  ram              — "8 GB" | "16 GB" | "24 GB"
  os               — "Windows 10" | "Windows 11" | "Linux" | "macOS"
  os_build         — "21H2" | "22H2" | "23H2" | "24H3"
  storage          — e.g. "512 GB SSD" | "1 TB" | "240 GB SSD"
  po_number        — "PORD/00217" or empty/NA
  location         — physical location string
  source_sheet     — office / location sheet name
  agreement_verified — verification text or ''
  agreement_doc    — filename or ''
  lifecycle        — lifecycle status string
  is_assigned      — "True" | "False"

Rules:
- Assign final result to `result`. No imports, no print(), no explanation.
- Use .str.lower().str.contains() for case-insensitive text matching.
- IT Stock: current_user.str.lower().str.contains('it stock|stock')
- Faulty: current_user or source_sheet contains 'fault|repair'
- RAM compare: df['ram'].str.extract(r'(\\d+)')[0].astype(float)
- Missing agreement: agreement_verified=='' AND agreement_doc=='' AND type=='Laptop'
- For counts/breakdowns: df.groupby('col').size().reset_index(name='Count')
- For missing fields: df['col'].str.strip() == ''
- Duplicates: df[df.duplicated(subset=['serial_no'], keep=False)]
"""


ANSWER_PROMPT = """You are a concise, professional IT Admin assistant.

Answer the user's question based ONLY on the inventory data provided.
- Be specific: include names, counts, serial numbers where relevant.
- Keep the response to 2–4 sentences.
- If data is empty, say no matching records were found and suggest a refinement.
- Do not repeat the full data table in your response."""


# ─── 1. Classify query ────────────────────────────────────────────────────────
def _llm(client: OpenAI, system: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 400) -> str:
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "system", "content": system}] + messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def classify(query: str, client: OpenAI) -> str:
    """Returns one of: "lookup" | "filter" | "aggregate" | "semantic" """
    category = _llm(client, CLASSIFIER_PROMPT, [{"role": "user", "content": query}], max_tokens=10).lower()
    return category if category in QUERY_TYPES else "semantic"


# ─── 2. Generate pandas code ──────────────────────────────────────────────────
def build_pandas_code(query: str, client: OpenAI, history: list[dict]) -> str:
    messages = [m for m in history[-6:] if m.get("role") in ("user", "assistant")]
    messages.append({"role": "user", "content": query})
    return _llm(client, PANDAS_CODE_PROMPT, messages)


# ─── 3. Generate natural language answer ─────────────────────────────────────
def generate(
    query:        str,
    context:      str,
    client:       OpenAI,
    history:      list[dict],
    record_count: int = 0,
) -> str:
    system_msg = ANSWER_PROMPT
    if record_count:
        system_msg += f"\n\nTotal matching records: {record_count}"

    messages = [m for m in history[-6:] if m.get("role") in ("user", "assistant")]
    messages.append({"role": "user", "content": f"Question: {query}\n\nInventory data:\n{context}"})
    return _llm(client, system_msg, messages, temperature=0.2, max_tokens=300)


# ─── Format retrieved records as context string ───────────────────────────────
def records_to_context(records: list[dict], max_records: int = 15) -> str:
    """Convert a list of metadata dicts into a readable context block for the LLM."""
    if not records:
        return "No matching records found."
    lines = []
    for i, r in enumerate(records[:max_records], 1):
        text = r.get("_text", "")
        sim  = r.get("_similarity", "")
        sim_label = f" [similarity: {sim}]" if sim else ""
        lines.append(f"Record {i}{sim_label}:\n  {text}")
    return "\n\n".join(lines)


def df_to_context(result: pd.DataFrame | pd.Series, max_rows: int = 20) -> str:
    """Convert a pandas result into a compact string for LLM context."""
    if isinstance(result, pd.DataFrame):
        if result.empty:
            return "Empty result — no matching records."
        return f"{len(result)} rows:\n{result.head(max_rows).to_string(index=False)}"
    if isinstance(result, pd.Series):
        return result.to_string()
    return str(result)
