"""
pipeline/sql_agent.py
---------------------
LangGraph SQL + RAG agent — full production architecture.
Uses Groq (llama-3.3-70b-versatile) via OpenAI-compatible API.

Full Graph
──────────
  START
    │
    ▼
  auth_check ── blocked ──────────────────────────────────────┐
    │                                                          │
    │ continue                                                 │
    ▼                                                          │
  classify ── (sql / semantic / action)                        │
    │                                                          │
    ▼                                                          │
  entity_extraction                                            │
    │                                                          │
    ▼                                                          │
  query_rewrite                                                │
    │                                                          │
    ├── sql ──► generate_sql ──► validate_sql                  │
    │                               │                          │
    │                    ┌──valid───┤                          │
    │                    │          │                          │
    │                    ▼    dangerous/invalid                 │
    │               execute_sql     │                          │
    │                    │          ▼                          │
    │           ┌────────┤       fix_sql ──► execute_sql       │
    │           │  error/│       (retry loop, max 3)           │
    │           │  empty │                                     │
    │           │        └── exhausted ──► semantic_search     │
    │           │                                              │
    │           └── success ──► confidence_check               │
    │                                                          │
    ├── semantic ──► semantic_search ──► confidence_check      │
    │                                                          │
    └── action ──► action_path ──► confidence_check            │
                                        │                      │
                                        ▼                      │
                                  generate_answer ◄────────────┘
                                        │
                                        ▼
                                   logging_node
                                        │
                                       END
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import TypedDict, Literal

import pandas as pd
from openai import OpenAI
from langgraph.graph import StateGraph, END

from pipeline.database import release_assets, write_audit_log

GROQ_MODEL = "llama-3.3-70b-versatile"

# ─── Dangerous SQL keywords the LLM should never generate ─────────────────────
_DANGEROUS_SQL = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH)\b",
    re.IGNORECASE,
)


# ─── Agent State ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # ── Core query fields ──
    query:            str
    rewritten_query:  str           # expanded/cleaned version after query_rewrite
    query_type:       str           # "sql" | "semantic" | "action"
    entities:         dict          # structured entities extracted from query

    # ── Auth ──
    username:         str
    user_role:        str           # "admin" | "viewer"
    blocked:          bool          # True if viewer tried a write action

    # ── SQL path ──
    sql_query:        str
    sql_valid:        bool          # False if validate_sql blocked it
    sql_result:       str
    sql_error:        str
    retry_count:      int

    # ── Action path ──
    action_type:      str           # "release" | "preview_release" | ""

    # ── Semantic path ──
    semantic_docs:    list[dict]

    # ── Answer ──
    confidence:       str           # "high" | "medium" | "low"
    final_answer:     str
    result_df:        list[dict]

    # ── Session ──
    history:          list[dict]


# ─── Prompts ──────────────────────────────────────────────────────────────────

_CLASSIFIER_PROMPT = """Classify this IT inventory query into exactly one of three categories:

  sql      → ANY data retrieval: lookups, filters, counts, lists, aggregations,
             reports, summaries, breakdowns, audits, or data health checks
  semantic → vague conceptual or open-ended recommendation questions with no
             specific data to retrieve
  action   → write operations: release devices, move to stock, assign assets

IMPORTANT: Reports, summaries, breakdowns, and data health queries are ALL "sql".
When in doubt, classify as "sql" — it is the correct choice for ~90% of queries.

Examples of SQL queries:
  "Which system does NTZ2186 use?"
  "What laptop does Anjali Garg have?"
  "Who is using host NTZ-LAP-045?"
  "Show all Windows 10 machines"
  "How many laptops are in CHD?"
  "List all machines with less than 16GB RAM"
  "Which devices are missing a serial number?"
  "Give me the full inventory summary"
  "Show the full data health report"
  "Asset count broken down by location"
  "Device breakdown by manufacturer"
  "List all Junior Software Engineers and their machines"
  "Show all EOL devices still assigned to users"
  "Assets with no PO number recorded"
  "Machines transferred from a previous user"
  "Are there any duplicate serial numbers?"
  "List all Lenovo E14 laptops"
  "Show machines with less than 16GB RAM"
  "Which laptops are missing an agreement?"
  "Show all verified laptop agreements"

Examples of action queries:
  "Release Anjali's devices"
  "Move NTZ2186 to IT Stock"
  "Free up all assets from the CHD office"

Examples of semantic queries (rare — only if truly no data to retrieve):
  "Which type of laptop is best for developers?"
  "What should I upgrade first?" (with no specific filter)

Reply with ONLY one word: sql  OR  semantic  OR  action
No punctuation, no explanation."""


_ENTITY_PROMPT = """Extract structured entities from this IT inventory query.
Return ONLY a valid JSON object with these exact keys (use null for missing values):

{
  "employee_name":  string or null,
  "employee_code":  string or null,
  "serial_no":      string or null,
  "host_name":      string or null,
  "device_type":    string or null,
  "os":             string or null,
  "os_build":       string or null,
  "ram":            string or null,
  "location":       string or null,
  "make":           string or null,
  "model":          string or null,
  "designation":    string or null,
  "po_number":      string or null,
  "lifecycle":      string or null
}

RULES
─────
employee_code:
  - Known patterns: NTZ\\d+, C\\d+, NIS\\d+ (e.g. NTZ2186, C1034, NIS042)
  - Any alphanumeric code that follows the words "Employee ID", "employee id",
    "emp id", "emp code", "employee no", "employee number" is an employee_code
    even if it does not match a known prefix pattern
  - Examples: "Employee ID 4521" → "4521", "emp code ABC99" → "ABC99"

host_name:
  - Patterns: NTZ-LAP-\\d+, NTZ-CPU-\\d+ (e.g. NTZ-LAP-045, NTZ-CPU-101)
  - Also match partial shorthand: "NTZ-115" or "LAP-045" — extract as-is

device_type:  normalise to exactly one of: Laptop / Desktop / MAC Mini
os:           normalise to exactly one of: Windows 10 / Windows 11 / Linux / macOS
os_build:     extract build version as uppercase (e.g. "21H2", "22H2", "23H2")
ram:          extract the number with unit (e.g. "16GB RAM" → "16 GB")
location:     office/city name (e.g. GGN, CHD, Mohali, Noida, 5th Floor)
designation:  job title or role (e.g. "Junior Software Engineer", "QA", "Manager")
po_number:    PO reference number (e.g. "PORD/00217")
lifecycle:    lifecycle or EOL status keywords (e.g. "EOL", "end of life", "expired")

EXAMPLES
────────
Query: "which system is used by employee ID NTZ2186?"
Output:
{
  "employee_name":  null,
  "employee_code":  "NTZ2186",
  "serial_no":      null,
  "host_name":      null,
  "device_type":    null,
  "os":             null,
  "os_build":       null,
  "ram":            null,
  "location":       null,
  "make":           null,
  "model":          null,
  "designation":    null,
  "po_number":      null,
  "lifecycle":      null
}

Query: "List all Junior Software Engineers and their machines"
Output:
{
  "employee_name":  null,
  "employee_code":  null,
  "serial_no":      null,
  "host_name":      null,
  "device_type":    null,
  "os":             null,
  "os_build":       null,
  "ram":            null,
  "location":       null,
  "make":           null,
  "model":          null,
  "designation":    "Junior Software Engineer",
  "po_number":      null,
  "lifecycle":      null
}

Return ONLY the JSON object. No explanation, no markdown fences."""


def _rewrite_prompt(schema: str) -> str:
    return f"""You are rewriting an IT inventory search query to be precise and SQL-friendly.

DATABASE SCHEMA
{schema}

KEY COLUMN REFERENCE (use these exact names in rewrites)
─────────────────────────────────────────────────────────
  current_user   — employee full name (e.g. "Anjali Garg")
  employee_code  — employee ID (e.g. NTZ2186, C1034)
  serial_no      — hardware serial number
  host_name      — device name (e.g. NTZ-LAP-045)
  type           — Laptop / Desktop / MAC Mini
  make           — manufacturer (e.g. Lenovo, Dell, Apple)
  model          — model name (e.g. E14, L14, M720t)
  os             — Windows 10 / Windows 11 / Linux / macOS
  os_build       — build version (e.g. 22H2, 21H2)
  ram            — e.g. "8 GB", "16 GB"
  storage        — e.g. "512 GB SSD"
  source_sheet   — office/location (e.g. GGN, CHD, Mohali, Noida, 5th Floor)
  designation    — job title / role
  po_number      — purchase order number
  lifecycle      — lifecycle/EOL status
  old_user       — previous user (non-empty means device was reassigned)
  is_assigned    — "True" if assigned to a person, "False" if in IT Stock
  agreement_verified, agreement_doc — laptop agreement fields

RULES
─────
1. If the query already clearly states a specific employee code, serial number,
   or host name — return it UNCHANGED. Do not paraphrase simple lookups.

2. Only rewrite if the query is ambiguous, uses informal shorthand, or mixes
   multiple implied fields.

3. When you do rewrite:
   - Use exact column names from the schema above
   - Expand host shorthand: "NTZ-115" → "host name NTZ-LAP-115 or NTZ-CPU-115"
   - Make intent explicit using column names
   - Keep it to ONE sentence

EXAMPLES OF GOOD REWRITES
──────────────────────────
Input : "which system does NTZ2186 use?"
Output: "which system does NTZ2186 use?"   ← unchanged, already clear

Input : "Anjali's laptop"
Output: "Show devices where current_user contains Anjali and type is Laptop"

Input : "NTZ-115"
Output: "Show device details for host_name NTZ-LAP-115 or NTZ-CPU-115"

Input : "machines needing upgrade"
Output: "List all devices where os is Windows 10 that are currently assigned"

Input : "all staff in GGN"
Output: "List all assigned devices where source_sheet is GGN"

Input : "junior engineers"
Output: "List all devices where designation contains Junior Software Engineer"

Input : "EOL laptops"
Output: "List all Laptop devices where lifecycle indicates end-of-life and is_assigned is True"

Input : "machines without a PO"
Output: "List all devices where po_number is empty"

Input : "reassigned devices"
Output: "List all devices where old_user is not empty"

Input : "devices under PO PORD/00217"
Output: "Show all devices where po_number is PORD/00217"

Return ONLY the rewritten query string. No explanation, no quotes around it."""


def _sql_gen_prompt(schema: str) -> str:
    return f"""You are an expert SQLite query writer for an IT asset inventory.

DATABASE SCHEMA
{schema}

CRITICAL COLUMN CLARIFICATIONS
───────────────────────────────
• current_user   — employee FULL NAME (e.g. "Anjali Garg"). Use for name searches.
                   "IT Stock [location]" when device is unassigned.
• employee_code  — employee ID (e.g. NTZ2186, C1034). Use for code searches.
• host_name      — device identifier (e.g. NTZ-LAP-045). Use for device name queries.
• serial_no      — hardware serial number. Use for serial number queries.
• source_sheet   — office/location name. Known values: GGN, CHD, Mohali, Noida,
                   5th Floor, 6th Floor, 7th Floor. Use for location queries.
• designation    — job title/role (e.g. "Junior Software Engineer", "QA Engineer").
• old_user       — previous user. Non-empty means the device was reassigned.
• po_number      — purchase order reference (e.g. "PORD/00217").
• lifecycle      — lifecycle/EOL status string.
• is_assigned    — stored as a STRING: 'True' or 'False' (not a boolean).
• os             — 'Windows 10' | 'Windows 11' | 'Linux' | 'macOS'
• type           — 'Laptop' | 'Desktop' | 'MAC Mini'

ALL string comparisons: use LOWER() + LIKE or LOWER() = LOWER(?).
ALL empty-field checks: use col = '' (NOT IS NULL — all fields are stored as strings).

═══════════════════════════════════════════════════════════════
LOOKUP PATTERNS — copy these exactly for the most common types
═══════════════════════════════════════════════════════════════

-- 1. By employee code (EXACT match — codes are identifiers):
SELECT current_user, employee_code, designation, type, make, model,
       serial_no, host_name, ram, os, os_build, storage, source_sheet
FROM inventory
WHERE LOWER(employee_code) = LOWER('NTZ2186')

-- 2. By employee name (LIKE — names may be partial):
SELECT current_user, employee_code, designation, type, make, model,
       serial_no, host_name, ram, os, source_sheet
FROM inventory
WHERE LOWER(current_user) LIKE '%anjali%'
  AND LOWER(is_assigned) = 'true'

-- 3. By host name (EXACT match):
SELECT current_user, employee_code, type, make, model,
       serial_no, ram, os, os_build, storage, source_sheet
FROM inventory
WHERE LOWER(host_name) = LOWER('NTZ-LAP-045')

-- 4. By serial number (EXACT match):
SELECT current_user, employee_code, type, make, model,
       host_name, ram, os, source_sheet
FROM inventory
WHERE LOWER(serial_no) = LOWER('PG02JT3N')

-- 5. By designation / job title:
SELECT current_user, employee_code, designation, type, make, model,
       serial_no, host_name, source_sheet
FROM inventory
WHERE LOWER(designation) LIKE '%junior software engineer%'
  AND LOWER(is_assigned) = 'true'
ORDER BY current_user

-- 6. By location / office:
SELECT current_user, employee_code, type, make, model, serial_no,
       host_name, os, source_sheet
FROM inventory
WHERE LOWER(source_sheet) LIKE '%ggn%'
  AND LOWER(is_assigned) = 'true'
ORDER BY current_user

-- 7. By make AND model:
SELECT current_user, employee_code, type, make, model,
       serial_no, host_name, ram, os, source_sheet
FROM inventory
WHERE LOWER(make) LIKE '%lenovo%'
  AND LOWER(model) LIKE '%e14%'
ORDER BY current_user

-- 8. By PO number (EXACT match):
SELECT current_user, employee_code, type, make, model,
       serial_no, host_name, po_number, source_sheet
FROM inventory
WHERE LOWER(po_number) = LOWER('PORD/00217')

-- 9. EOL / lifecycle devices still assigned:
SELECT current_user, employee_code, designation, type, make, model,
       serial_no, lifecycle, source_sheet
FROM inventory
WHERE lifecycle != ''
  AND LOWER(is_assigned) = 'true'
ORDER BY current_user

-- 10. Reassigned devices (old_user is not empty):
SELECT current_user, old_user, employee_code, type, make, model,
       serial_no, host_name, source_sheet
FROM inventory
WHERE old_user != ''
ORDER BY current_user

-- 11. IT Stock (unassigned devices):
SELECT type, make, model, serial_no, host_name, ram, os, source_sheet
FROM inventory
WHERE LOWER(current_user) LIKE '%it stock%'
ORDER BY type, make

-- 12. Faulty / repair devices:
SELECT current_user, type, make, model, serial_no, source_sheet
FROM inventory
WHERE LOWER(current_user) LIKE '%fault%'
   OR LOWER(source_sheet) LIKE '%fault%'

-- 13. Missing agreement (laptops only):
SELECT current_user, employee_code, type, serial_no, source_sheet
FROM inventory
WHERE agreement_verified = ''
  AND agreement_doc = ''
  AND LOWER(type) = 'laptop'
  AND LOWER(is_assigned) = 'true'
ORDER BY current_user

-- 14. Missing PO number:
SELECT current_user, employee_code, type, make, model, serial_no
FROM inventory
WHERE po_number = ''
  AND LOWER(is_assigned) = 'true'
ORDER BY current_user

-- 15. Missing serial number:
SELECT current_user, employee_code, type, make, model, host_name, source_sheet
FROM inventory
WHERE serial_no = ''
ORDER BY current_user

-- 16. Duplicate serial numbers:
SELECT serial_no, COUNT(*) AS duplicate_count,
       GROUP_CONCAT(current_user, ' / ') AS users
FROM inventory
WHERE serial_no != ''
GROUP BY serial_no
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC

-- 17. Count by location (breakdown):
SELECT source_sheet AS location, COUNT(*) AS total_devices,
       SUM(CASE WHEN LOWER(type) = 'laptop' THEN 1 ELSE 0 END) AS laptops,
       SUM(CASE WHEN LOWER(type) = 'desktop' THEN 1 ELSE 0 END) AS desktops
FROM inventory
WHERE LOWER(is_assigned) = 'true'
GROUP BY source_sheet
ORDER BY total_devices DESC

-- 18. Count by manufacturer (breakdown):
SELECT make, COUNT(*) AS total,
       SUM(CASE WHEN LOWER(type) = 'laptop' THEN 1 ELSE 0 END) AS laptops,
       SUM(CASE WHEN LOWER(type) = 'desktop' THEN 1 ELSE 0 END) AS desktops
FROM inventory
WHERE make != ''
GROUP BY make
ORDER BY total DESC

-- 19. Full inventory summary (counts by type + OS + assignment):
SELECT
  COUNT(*) AS total_records,
  SUM(CASE WHEN LOWER(type) = 'laptop' THEN 1 ELSE 0 END) AS laptops,
  SUM(CASE WHEN LOWER(type) = 'desktop' THEN 1 ELSE 0 END) AS desktops,
  SUM(CASE WHEN LOWER(type) = 'mac mini' THEN 1 ELSE 0 END) AS mac_mini,
  SUM(CASE WHEN LOWER(is_assigned) = 'true' THEN 1 ELSE 0 END) AS assigned,
  SUM(CASE WHEN LOWER(current_user) LIKE '%it stock%' THEN 1 ELSE 0 END) AS in_stock,
  SUM(CASE WHEN LOWER(os) LIKE '%windows 10%' THEN 1 ELSE 0 END) AS windows_10,
  SUM(CASE WHEN LOWER(os) LIKE '%windows 11%' THEN 1 ELSE 0 END) AS windows_11,
  SUM(CASE WHEN serial_no = '' THEN 1 ELSE 0 END) AS missing_serial
FROM inventory

-- 20. RAM filter (less than / greater than):
SELECT current_user, employee_code, type, make, model, ram, source_sheet
FROM inventory
WHERE CAST(TRIM(REPLACE(REPLACE(REPLACE(ram, ' GB', ''), 'GB', ''), 'gb', '')) AS INTEGER) < 16
  AND ram != ''
  AND LOWER(is_assigned) = 'true'
ORDER BY CAST(TRIM(REPLACE(REPLACE(REPLACE(ram, ' GB', ''), 'GB', ''), 'gb', '')) AS INTEGER)

═══════════════════════════════════════════════════════════════
GENERAL RULES
═══════════════════════════════════════════════════════════════
• Table name         : inventory
• Exact identifiers  : use LOWER(col) = LOWER('value') — never LIKE
• Partial text       : use LOWER(col) LIKE '%value%'
• Empty field check  : col = ''  (never IS NULL)
• IT Stock filter    : LOWER(current_user) LIKE '%it stock%'
• is_assigned        : LOWER(is_assigned) = 'true'  or  = 'false'
• OS build filter    : UPPER(os_build) = '22H2'
• Always SELECT named columns — avoid SELECT *
• Add ORDER BY for readability
• Add LIMIT 100 for row-level queries; omit for COUNT/GROUP BY queries

OUTPUT: Return ONLY the raw SQL query. No markdown fences, no backticks, no explanation."""

def _sql_fix_prompt(schema: str) -> str:
    return f"""A SQLite query failed. Rewrite it to fix the error.

DATABASE SCHEMA (use this to correct column names and values):
{schema}

CRITICAL COLUMN CLARIFICATIONS
───────────────────────────────
• employee_code  — employee ID (NTZ2186, C1034). NOT "employee_id" or "emp_code" or "id".
• current_user   — employee's full name. NOT the employee code, NOT "username" or "user".
• host_name      — device name (NTZ-LAP-045). NOT "hostname" or "host_id" or "computer_name".
• source_sheet   — office/location. NOT "location" or "office" or "city".
• designation    — job title. NOT "role" or "job_title" or "position".
• po_number      — purchase order. NOT "po" or "purchase_order" or "order_no".
• old_user       — previous user. NOT "previous_user" or "former_user".
• lifecycle      — lifecycle status. NOT "eol" or "end_of_life" or "age".
• is_assigned    — stored as STRING 'True'/'False'. NOT a boolean. Use LOWER(is_assigned) = 'true'.
• agreement_verified, agreement_doc — NOT "agreement" or "laptop_agreement".

COMMON FIX SCENARIOS
─────────────────────
• "no such column: employee_id"     → use employee_code
• "no such column: hostname"        → use host_name
• "no such column: computer_name"   → use host_name
• "no such column: location"        → use source_sheet
• "no such column: office"          → use source_sheet
• "no such column: name"            → use current_user
• "no such column: username"        → use current_user
• "no such column: role"            → use designation
• "no such column: job_title"       → use designation
• "no such column: purchase_order"  → use po_number
• "no such column: eol"             → use lifecycle
• Wrong os value                    → use 'Windows 10' or 'Windows 11' (not 'win10', 'w10')
• Wrong type value                  → use 'Laptop' / 'Desktop' / 'MAC Mini'
• Used LIKE for code/serial/host    → change to = for exact match
• IS NULL for empty field           → change to col = ''
• Boolean is_assigned               → change to LOWER(is_assigned) = 'true' or 'false'
• RAM comparison without CAST       → use CAST(TRIM(REPLACE(REPLACE(REPLACE(ram,' GB',''),'GB',''),'gb','')) AS INTEGER)

Rules:
• Table: inventory  |  SQLite syntax only
• Exact identifiers (code, serial, host, PO): use LOWER(col) = LOWER('value')
• Names, titles, descriptions: use LOWER(col) LIKE '%value%'
• Empty field check: col = '' (never IS NULL)
• Return ONLY the corrected raw SQL — no markdown fences, no explanation."""

def _answer_prompt(is_list_query: bool, confidence: str, blocked: bool) -> str:
    if blocked:
        return """You are a professional IT Admin assistant.
The user tried to perform a write operation but does not have permission.
Respond with a clear, polite message explaining they need admin access for this action.
Keep it to 1 sentence."""

    confidence_note = {
        "high":   "",
        "medium": "\nIMPORTANT: End your answer with one sentence noting these are the closest matches found; the user may want to refine their search.",
        "low":    "\nIMPORTANT: Be upfront that no exact match was found. State what was searched and suggest a specific refinement (different spelling, employee code instead of name, etc.).",
    }.get(confidence, "")

    if is_list_query:
        return f"""You are a professional IT Admin assistant.

The user asked a question that returned a list of inventory records.
Write a clear 1-2 sentence summary of what was found:
  - State the count and category (e.g. "Found 14 laptops running Windows 10 across 3 locations.")
  - For breakdowns/reports: briefly mention the top finding or most notable number.
  - For data health queries: highlight any problem counts (missing, duplicate, unverified).
  - For location/make breakdowns: name the top location or manufacturer.
Do NOT reproduce the rows — the data table is shown separately below your answer.{confidence_note}"""

    return f"""You are a concise, professional IT Admin assistant.

Answer the user's question using ONLY the inventory data provided.

For SINGLE RECORD lookups (one person / one device):
  State all key fields in natural language — device type, make and model,
  serial number, host name, RAM, OS, OS build, storage, location (source_sheet),
  and designation if available. Mention the employee name and code.
  Example: "Anjali Garg (NTZ2186, Senior QA Engineer) is using a Lenovo E14 Laptop
  (Serial: PG02JT3N, Host: NTZ-LAP-045) — 16 GB RAM, Windows 11 22H2,
  512 GB SSD, located in the GGN office."

For COUNTS / AGGREGATES:
  State the exact number and the most important breakdown figures.

For EMPTY results:
  Say clearly that no records were found. Suggest a concrete refinement
  (e.g. try employee code instead of name, check spelling, broaden the filter).

Keep it to 2–4 sentences. Do NOT reproduce the full data table.{confidence_note}"""


_ACTION_PROMPT = """You are an IT Admin assistant.
The user wants to perform an asset release / device return action.

Based on the query and extracted entities, write a clear confirmation preview message:
- State who the devices belong to (name or code)
- Mention that this is a preview — no changes have been made yet
- Tell the user to use the 'Asset Release' tab to confirm the actual release
- Keep it to 2-3 sentences, professional tone."""


# ─── Helpers ──────────────────────────────────────────────────────────────────

_CODE_FENCE_RE = re.compile(r"^```[\w]*\n?|```$", re.MULTILINE)


def _strip_sql(raw: str) -> str:
    cleaned = _CODE_FENCE_RE.sub("", raw).strip()
    if re.match(r"^sql\b", cleaned, re.IGNORECASE):
        cleaned = cleaned[3:].strip()
    return cleaned


def _parse_json_safe(text: str) -> dict:
    """Parse LLM JSON output, stripping fences and handling partial output."""
    cleaned = _CODE_FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # Try to extract anything between first { and last }
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def _is_list_query(query: str, sql: str) -> bool:
    q = query.lower()
    count_kw = ["how many", "count", "total", "number of"]
    list_kw  = ["list", "show all", "all machines", "all laptops", "all devices",
                "all employees", "give me all", "which machines", "which laptops",
                "which devices", "which employees", "who are", "find all"]
    if any(k in q for k in count_kw):
        return False
    if any(k in q for k in list_kw):
        return True
    sql_upper = sql.upper()
    return "GROUP BY" not in sql_upper and "COUNT(" not in sql_upper


def _determine_path(state: AgentState) -> str:
    if state.get("blocked"):
        return "blocked"
    if state.get("action_type"):
        return f"action:{state['action_type']}"
    if state.get("result_df"):
        return "sql_success" if state.get("sql_query") else "semantic_success"
    if state.get("semantic_docs"):
        return "sql→semantic_fallback" if state.get("sql_query") else "semantic"
    return "no_results"


# ─── Node factory ─────────────────────────────────────────────────────────────

def make_nodes(
    openai_client: OpenAI,
    db_conn:       sqlite3.Connection,
    schema:        str,
    retriever,
):
    def _llm(
        system:      str,
        messages:    list[dict],
        temperature: float = 0.0,
        max_tokens:  int   = 400,
    ) -> str:
        resp = openai_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    # ── 1. Auth Check ─────────────────────────────────────────────────────────
    def auth_check_node(state: AgentState) -> AgentState:
        """
        Block viewers from write/action operations before any LLM call is made.
        Reads username and user_role injected by chain.query().
        """
        role  = state.get("user_role", "viewer")
        query = state.get("query", "").lower()

        # Simple heuristic to detect write intent before the full classify call
        write_keywords = [
            "release", "move to stock", "free up", "transfer", "assign",
            "unassign", "remove from", "return device",
        ]
        is_write_intent = any(k in query for k in write_keywords)

        if role != "admin" and is_write_intent:
            return {**state, "blocked": True, "query_type": "action"}

        return {**state, "blocked": False}

    # ── 2. Classify ───────────────────────────────────────────────────────────
    def classify_node(state: AgentState) -> AgentState:
        raw   = _llm(
            _CLASSIFIER_PROMPT,
            [{"role": "user", "content": state["query"]}],
            max_tokens=15,
        ).lower().strip().rstrip(".,;:!")

        qtype = raw if raw in ("sql", "semantic", "action") else "sql"
        return {**state, "query_type": qtype}

    # ── 3. Entity Extraction ──────────────────────────────────────────────────
    def entity_extraction_node(state: AgentState) -> AgentState:
        """
        Extract structured entities from the query (name, code, serial, host,
        device type, OS, RAM, location, make, model) as a JSON dict.
        """
        raw  = _llm(
            _ENTITY_PROMPT,
            [{"role": "user", "content": state["query"]}],
            max_tokens=200,
        )
        entities = _parse_json_safe(raw)

        # Also try regex extraction as a reliable fallback for common patterns
        q = state["query"]
        if not entities.get("employee_code"):
            m = re.search(r"\b(NTZ|C|NIS)\d+\b", q, re.IGNORECASE)
            if m:
                entities["employee_code"] = m.group(0).upper()

        if not entities.get("host_name"):
            m = re.search(r"\b(NTZ|SWJ|NA)-(LAP|CPU)-\d+\b", q, re.IGNORECASE)
            if m:
                entities["host_name"] = m.group(0).upper()

        # Detect bare host shorthand e.g. "NTZ-115" → expand to both variants
        m = re.search(r"\b(NTZ|SWJ|NA)-(\d+)\b", q, re.IGNORECASE)
        if m and not entities.get("host_name"):
            prefix = m.group(1).upper()
            num    = m.group(2)
            entities["host_name_expanded"] = [
                f"{prefix}-LAP-{num.zfill(3)}",
                f"{prefix}-CPU-{num.zfill(3)}",
            ]

        return {**state, "entities": entities}

    # ── 4. Query Rewrite ──────────────────────────────────────────────────────
    def query_rewrite_node(state: AgentState) -> AgentState:
        """
        Use extracted entities to produce a cleaner, more SQL-friendly query.
        Falls back to original query if rewrite fails or adds no value.
        """
        entities = state.get("entities", {})
        # Only rewrite if we actually extracted something useful
        if not any(v for v in entities.values() if v):
            return {**state, "rewritten_query": state["query"]}

        entity_str = json.dumps(
            {k: v for k, v in entities.items() if v},
            indent=2,
        )
        prompt_input = (
            f"Original query: {state['query']}\n\n"
            f"Extracted entities:\n{entity_str}"
        )
        rewritten = _llm(
            _rewrite_prompt(schema),
            [{"role": "user", "content": prompt_input}],
            max_tokens=120,
        ).strip().strip('"')

        # Sanity check: if it's way longer than original it's probably hallucinating
        if len(rewritten) > len(state["query"]) * 4:
            rewritten = state["query"]

        return {**state, "rewritten_query": rewritten}

    # ── 5. Generate SQL ───────────────────────────────────────────────────────
    def generate_sql_node(state: AgentState) -> AgentState:
        effective_query = state.get("rewritten_query") or state["query"]

        messages = [
            msg for msg in state["history"][-6:]
            if msg.get("role") in ("user", "assistant")
        ]
        messages.append({"role": "user", "content": effective_query})

        raw_sql = _llm(_sql_gen_prompt(schema), messages).strip()
        sql     = _strip_sql(raw_sql)
        return {**state, "sql_query": sql, "sql_error": "", "sql_valid": True}

    # ── 6. Validate SQL ───────────────────────────────────────────────────────
    def validate_sql_node(state: AgentState) -> AgentState:
        """
        Two checks before executing:
        1. Dangerous keywords (DROP, DELETE, UPDATE etc.) → dangerous
        2. SQL is clearly malformed or empty → invalid
        Valid SELECT queries pass through.
        """
        sql = state.get("sql_query", "").strip()

        if not sql:
            return {
                **state,
                "sql_valid": False,
                "sql_error": "Empty SQL generated.",
            }

        if _DANGEROUS_SQL.search(sql):
            return {
                **state,
                "sql_valid": False,
                "sql_error": f"Dangerous SQL keyword detected — blocked for safety.",
            }

        # Must start with SELECT (after any comments)
        sql_clean = re.sub(r"--[^\n]*", "", sql).strip()
        if not sql_clean.upper().startswith("SELECT"):
            return {
                **state,
                "sql_valid": False,
                "sql_error": "Only SELECT queries are permitted.",
            }

        return {**state, "sql_valid": True}

    # ── 7. Execute SQL ────────────────────────────────────────────────────────
    def execute_sql_node(state: AgentState) -> AgentState:
        try:
            df = pd.read_sql_query(state["sql_query"], db_conn)
            if df.empty:
                return {
                    **state,
                    "sql_result":  "Query returned 0 rows.",
                    "sql_error":   "",
                    "result_df":   [],
                }
            result_str = (
                f"{len(df)} row(s) returned.\n"
                f"{df.head(20).to_string(index=False)}"
            )
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

    # ── 8. Fix SQL ────────────────────────────────────────────────────────────
    def fix_sql_node(state: AgentState) -> AgentState:
        user_content = (
            f"Question : {state.get('rewritten_query') or state['query']}\n"
            f"Failed SQL:\n{state['sql_query']}\n"
            f"Error     : {state['sql_error']}"
        )
        raw_fixed = _llm(
            _sql_fix_prompt(schema),
            [{"role": "user", "content": user_content}],
        ).strip()
        fixed = _strip_sql(raw_fixed)
        return {**state, "sql_query": fixed, "sql_valid": True}

    # ── 9. Action Path ────────────────────────────────────────────────────────
    def action_path_node(state: AgentState) -> AgentState:
        """
        Handles write-intent queries detected by classify.

        For safety, chat-triggered actions are PREVIEW ONLY — they show what
        would be affected but do not execute. The actual write is done through
        the dedicated Asset Release tab in the UI (which has its own confirm step).

        This keeps the chat interface read-safe while still being helpful.
        """
        entities = state.get("entities", {})
        identifier = (
            entities.get("employee_name") or
            entities.get("employee_code") or
            ""
        )

        result_df = []

        if identifier:
            like_pattern = f"%{identifier}%"
            try:
                preview_df = pd.read_sql_query(
                    """
                    SELECT current_user, employee_code, type, make, model,
                           serial_no, host_name, source_sheet
                    FROM   inventory
                    WHERE  (LOWER(current_user)  LIKE LOWER(?)
                         OR LOWER(employee_code) LIKE LOWER(?))
                      AND  LOWER(is_assigned) = 'true'
                    """,
                    db_conn,
                    params=(like_pattern, like_pattern),
                )
                result_df = preview_df.astype(str).to_dict(orient="records")
            except Exception:
                pass

        messages = [{"role": "user", "content": (
            f"Query: {state['query']}\n"
            f"Entities: {json.dumps({k: v for k, v in entities.items() if v})}\n"
            f"Devices found: {len(result_df)}"
        )}]
        answer = _llm(_ACTION_PROMPT, messages, temperature=0.2, max_tokens=200)

        return {
            **state,
            "action_type": "preview_release",
            "result_df":   result_df,
            "final_answer": answer,
        }

    # ── 10. Semantic Search ───────────────────────────────────────────────────
    def semantic_search_node(state: AgentState) -> AgentState:
        if retriever is None:
            return {**state, "semantic_docs": []}
        # Use the rewritten query for better semantic matching
        effective_query = state.get("rewritten_query") or state["query"]
        docs = retriever.search(effective_query, n_results=12)
        return {**state, "semantic_docs": docs}

    # ── 11. Confidence Check ──────────────────────────────────────────────────
    def confidence_check_node(state: AgentState) -> AgentState:
        """
        Score result confidence based on what was found and how.

        high   — SQL returned rows / action preview found devices
        medium — semantic search found results with decent similarity
        low    — 0 rows everywhere, or very low similarity scores
        """
        if state.get("result_df"):
            # SQL or action path found real rows
            confidence = "high"

        elif state.get("semantic_docs"):
            scores = [
                d.get("_similarity", 0)
                for d in state["semantic_docs"]
                if "_similarity" in d
            ]
            avg_score = sum(scores) / len(scores) if scores else 0
            confidence = "medium" if avg_score >= 0.45 else "low"

        else:
            confidence = "low"

        return {**state, "confidence": confidence}

    # ── 12. Generate Answer ───────────────────────────────────────────────────
    def generate_answer_node(state: AgentState) -> AgentState:
        # Action path already built its own answer
        if state.get("action_type") and state.get("final_answer"):
            return state

        blocked    = state.get("blocked", False)
        confidence = state.get("confidence", "high")
        sql        = state.get("sql_query", "")
        is_list    = _is_list_query(state["query"], sql)

        if blocked:
            context = ""
        elif state.get("result_df"):
            context = f"[SQL Result]\n{state['sql_result']}"
        elif state.get("semantic_docs"):
            lines   = [d.get("_text", str(d)) for d in state["semantic_docs"][:12]]
            context = "[Semantic Search Results]\n" + "\n\n".join(lines)
        else:
            context = "No matching data found in the inventory."

        messages = [
            msg for msg in state["history"][-6:]
            if msg.get("role") in ("user", "assistant")
        ]
        messages.append({
            "role": "user",
            "content": f"Question: {state['query']}\n\nData:\n{context}",
        })

        answer = _llm(
            _answer_prompt(is_list, confidence, blocked),
            messages,
            temperature=0.2,
            max_tokens=400,
        )
        return {**state, "final_answer": answer}

    # ── 13. Logging ───────────────────────────────────────────────────────────
    def logging_node(state: AgentState) -> AgentState:
        """
        Write a structured audit log entry to the audit_log table.
        Non-blocking — any failure is silently caught so it never breaks a response.
        """
        try:
            answer_preview = (state.get("final_answer") or "")[:200]
            write_audit_log(db_conn, {
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "username":        state.get("username", "unknown"),
                "user_role":       state.get("user_role", "viewer"),
                "original_query":  state.get("query", ""),
                "rewritten_query": state.get("rewritten_query", ""),
                "query_type":      state.get("query_type", ""),
                "action_type":     state.get("action_type", ""),
                "sql_generated":   state.get("sql_query", ""),
                "row_count":       len(state.get("result_df", [])),
                "confidence":      state.get("confidence", ""),
                "path_taken":      _determine_path(state),
                "answer_preview":  answer_preview,
            })
        except Exception:
            pass  # logging must never break the main response
        return state

    return (
        auth_check_node,
        classify_node,
        entity_extraction_node,
        query_rewrite_node,
        generate_sql_node,
        validate_sql_node,
        execute_sql_node,
        fix_sql_node,
        action_path_node,
        semantic_search_node,
        confidence_check_node,
        generate_answer_node,
        logging_node,
    )


# ─── Routing conditions ───────────────────────────────────────────────────────

def _route_auth(state: AgentState) -> Literal["blocked", "continue"]:
    return "blocked" if state.get("blocked") else "continue"


def _route_classify(state: AgentState) -> Literal["sql", "semantic", "action"]:
    qt = state.get("query_type", "sql")
    return qt if qt in ("sql", "semantic", "action") else "sql"


def _route_validate(state: AgentState) -> Literal["valid", "dangerous"]:
    """
    valid     → execute_sql
    dangerous → semantic_search (don't retry genuinely dangerous/blocked SQL)
    """
    return "valid" if state.get("sql_valid", True) else "dangerous"


def _route_execute(
    state: AgentState,
) -> Literal["success", "retry", "exhausted", "empty_fallback"]:
    if state.get("sql_error"):
        return "retry" if state.get("retry_count", 0) < 3 else "exhausted"
    if not state.get("result_df"):
        return "empty_fallback"
    return "success"


# ─── Graph builder ────────────────────────────────────────────────────────────

def build_graph(
    openai_client: OpenAI,
    db_conn:       sqlite3.Connection,
    schema:        str,
    retriever,
):
    (
        auth_check_node,
        classify_node,
        entity_extraction_node,
        query_rewrite_node,
        generate_sql_node,
        validate_sql_node,
        execute_sql_node,
        fix_sql_node,
        action_path_node,
        semantic_search_node,
        confidence_check_node,
        generate_answer_node,
        logging_node,
    ) = make_nodes(openai_client, db_conn, schema, retriever)

    g = StateGraph(AgentState)

    # ── Register nodes ──
    g.add_node("auth_check",         auth_check_node)
    g.add_node("classify",           classify_node)
    g.add_node("entity_extraction",  entity_extraction_node)
    g.add_node("query_rewrite",      query_rewrite_node)
    g.add_node("generate_sql",       generate_sql_node)
    g.add_node("validate_sql",       validate_sql_node)
    g.add_node("execute_sql",        execute_sql_node)
    g.add_node("fix_sql",            fix_sql_node)
    g.add_node("action_path",        action_path_node)
    g.add_node("semantic_search",    semantic_search_node)
    g.add_node("confidence_check",   confidence_check_node)
    g.add_node("generate_answer",    generate_answer_node)
    g.add_node("logging_node",       logging_node)

    # ── Entry ──
    g.set_entry_point("auth_check")

    # auth_check → blocked goes straight to generate_answer (returns permission error)
    # auth_check → continue goes to classify
    g.add_conditional_edges(
        "auth_check",
        _route_auth,
        {"blocked": "generate_answer", "continue": "classify"},
    )

    # classify → entity_extraction (always, regardless of type)
    g.add_edge("classify", "entity_extraction")
    g.add_edge("entity_extraction", "query_rewrite")

    # query_rewrite → branch on query_type
    g.add_conditional_edges(
        "query_rewrite",
        _route_classify,
        {
            "sql":      "generate_sql",
            "semantic": "semantic_search",
            "action":   "action_path",
        },
    )

    # SQL path
    g.add_edge("generate_sql", "validate_sql")
    g.add_conditional_edges(
        "validate_sql",
        _route_validate,
        {"valid": "execute_sql", "dangerous": "semantic_search"},
    )
    g.add_conditional_edges(
        "execute_sql",
        _route_execute,
        {
            "success":        "confidence_check",
            "retry":          "fix_sql",
            "exhausted":      "semantic_search",
            "empty_fallback": "semantic_search",
        },
    )
    g.add_edge("fix_sql", "execute_sql")

    # Semantic + action converge on confidence_check
    g.add_edge("semantic_search", "confidence_check")
    g.add_edge("action_path",     "confidence_check")

    # confidence_check → generate_answer → logging → END
    g.add_edge("confidence_check", "generate_answer")
    g.add_edge("generate_answer",  "logging_node")
    g.add_edge("logging_node",     END)

    return g.compile()