"""
pipeline/database.py
--------------------
Converts master_inventory.csv → SQLite database.

Responsibilities:
  - setup_database()    : load CSV, create table, add indexes
  - get_schema()        : return LLM-readable schema + sample values
  - execute_query()     : run a SQL string and return a DataFrame
  - init_audit_log()    : create audit_log table on first startup
  - write_audit_log()   : append one entry to audit_log (called by logging_node)
  - release_assets()    : employee exit — move devices to IT Stock
  - get_stock_summary() : unassigned devices grouped by type/make/location
  - predict_requirements(), gap_analysis(), procurement_suggestions()
"""

import sqlite3
from datetime import datetime, timezone

import pandas as pd

TABLE     = "inventory"
LOG_TABLE = "audit_log"


# ─── Setup ────────────────────────────────────────────────────────────────────

def setup_database(csv_path: str, db_path: str) -> sqlite3.Connection:
    """
    Create / refresh the SQLite database from the CSV.
    Also ensures the audit_log table exists.
    """
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    conn = sqlite3.connect(db_path, check_same_thread=False)

    # Check if already loaded and up-to-date
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        if count == len(df):
            print(f"[database] SQLite already has {count} records. Skipping re-creation.")
            init_audit_log(conn)
            return conn
    except Exception:
        pass

    conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
    df.to_sql(TABLE, conn, if_exists="replace", index=False)

    for col in [
        "current_user", "employee_code", "serial_no",
        "type", "os", "make", "source_sheet", "host_name",
    ]:
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON {TABLE}({col})")

    conn.commit()
    print(f"[database] SQLite ready: {len(df)} rows in '{TABLE}' table at {db_path}")

    init_audit_log(conn)
    return conn


# ─── Query execution ──────────────────────────────────────────────────────────

def execute_query(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


# ─── Schema for LLM ──────────────────────────────────────────────────────────

def get_schema(conn: sqlite3.Connection) -> str:
    cursor  = conn.execute(f"PRAGMA table_info({TABLE})")
    columns = [row[1] for row in cursor.fetchall()]

    sample_cols = ["type", "make", "os", "os_build", "ram", "source_sheet", "designation"]
    samples: dict[str, list[str]] = {}
    for col in sample_cols:
        try:
            rows = conn.execute(
                f"SELECT DISTINCT {col} FROM {TABLE} "
                f"WHERE {col} != '' ORDER BY {col} LIMIT 6"
            ).fetchall()
            vals = [r[0] for r in rows if r[0]]
            if vals:
                samples[col] = vals
        except Exception:
            pass

    total = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]

    lines = [
        f"Table : {TABLE}",
        f"Rows  : {total}",
        f"Columns: {', '.join(columns)}",
        "",
        "Key column sample values:",
    ]
    for col, vals in samples.items():
        lines.append(f"  {col}: {vals}")

    return "\n".join(lines)


# ─── Audit Log ────────────────────────────────────────────────────────────────

def init_audit_log(conn: sqlite3.Connection) -> None:
    """
    Create the audit_log table if it doesn't exist.
    Called once at startup from setup_database().
    """
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {LOG_TABLE} (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp        TEXT    NOT NULL,
            username         TEXT    NOT NULL,
            user_role        TEXT    NOT NULL,
            original_query   TEXT,
            rewritten_query  TEXT,
            query_type       TEXT,
            action_type      TEXT,
            sql_generated    TEXT,
            row_count        INTEGER DEFAULT 0,
            confidence       TEXT,
            path_taken       TEXT,
            answer_preview   TEXT
        )
    """)
    conn.commit()
    print(f"[database] audit_log table ready.")


def write_audit_log(conn: sqlite3.Connection, entry: dict) -> None:
    """
    Append one structured row to the audit_log table.

    Expected entry keys:
        timestamp, username, user_role, original_query, rewritten_query,
        query_type, action_type, sql_generated, row_count, confidence,
        path_taken, answer_preview

    Silently ignores errors so a logging failure never breaks a response.
    """
    try:
        conn.execute(
            f"""
            INSERT INTO {LOG_TABLE} (
                timestamp, username, user_role,
                original_query, rewritten_query,
                query_type, action_type, sql_generated,
                row_count, confidence, path_taken, answer_preview
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("timestamp", datetime.now(timezone.utc).isoformat()),
                entry.get("username",        "unknown"),
                entry.get("user_role",       "viewer"),
                entry.get("original_query",  ""),
                entry.get("rewritten_query", ""),
                entry.get("query_type",      ""),
                entry.get("action_type",     ""),
                entry.get("sql_generated",   ""),
                int(entry.get("row_count",   0)),
                entry.get("confidence",      ""),
                entry.get("path_taken",      ""),
                entry.get("answer_preview",  "")[:200],
            ),
        )
        conn.commit()
    except Exception as exc:
        print(f"[audit_log] Write failed (non-fatal): {exc}")


# ─── Asset Release (Employee Exit) ───────────────────────────────────────────

def release_assets(
    conn:         sqlite3.Connection,
    identifier:   str,
    new_location: str = "IT Stock",
) -> pd.DataFrame:
    like_pattern = f"%{identifier}%"

    devices = pd.read_sql_query(
        f"""
        SELECT rowid, *
        FROM   {TABLE}
        WHERE  (LOWER(current_user)  LIKE LOWER(?)
             OR LOWER(employee_code) LIKE LOWER(?))
          AND  LOWER(is_assigned) = 'true'
        """,
        conn,
        params=(like_pattern, like_pattern),
    )

    if devices.empty:
        return devices

    stock_label = f"IT Stock {new_location}".strip()
    for _, row in devices.iterrows():
        conn.execute(
            f"""
            UPDATE {TABLE}
            SET    old_user     = current_user,
                   current_user = ?,
                   is_assigned  = 'False'
            WHERE  rowid = ?
            """,
            (stock_label, int(row["rowid"])),
        )

    conn.commit()
    return devices


# ─── Stock Visibility ─────────────────────────────────────────────────────────

def get_stock_summary(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        f"""
        SELECT
            type,
            make,
            source_sheet      AS location,
            COUNT(*)          AS available_count
        FROM   {TABLE}
        WHERE  LOWER(current_user) LIKE '%it stock%'
           AND type != ''
        GROUP  BY type, make, source_sheet
        ORDER  BY available_count DESC
        """,
        conn,
    )


# ─── Future Requirement Prediction ───────────────────────────────────────────

def predict_requirements(
    conn:        sqlite3.Connection,
    new_joiners: int,
) -> pd.DataFrame:
    dist = pd.read_sql_query(
        f"""
        SELECT type, COUNT(*) AS cnt
        FROM   {TABLE}
        WHERE  LOWER(is_assigned) = 'true'
          AND  type != ''
        GROUP  BY type
        """,
        conn,
    )
    if dist.empty or new_joiners <= 0:
        return pd.DataFrame(columns=["Type", "Predicted Need"])

    total           = dist["cnt"].sum()
    dist["ratio"]   = dist["cnt"] / total
    dist["Predicted Need"] = (dist["ratio"] * new_joiners).round().astype(int)
    dist = dist.rename(columns={"type": "Type"})[["Type", "Predicted Need"]]
    return dist[dist["Predicted Need"] > 0].reset_index(drop=True)


# ─── Gap Analysis ─────────────────────────────────────────────────────────────

def gap_analysis(conn: sqlite3.Connection, new_joiners: int) -> pd.DataFrame:
    stock = pd.read_sql_query(
        f"""
        SELECT type, COUNT(*) AS in_stock
        FROM   {TABLE}
        WHERE  LOWER(current_user) LIKE '%it stock%'
          AND  type != ''
        GROUP  BY type
        """,
        conn,
    )
    prediction = predict_requirements(conn, new_joiners)
    if prediction.empty:
        return pd.DataFrame()

    merged = prediction.merge(
        stock.rename(columns={"type": "Type"}), on="Type", how="left"
    ).fillna(0)

    merged["In Stock"]       = merged["in_stock"].astype(int)
    merged["Predicted Need"] = merged["Predicted Need"].astype(int)
    merged["Gap"]            = merged["In Stock"] - merged["Predicted Need"]
    merged["Status"]         = merged["Gap"].apply(
        lambda g: "Sufficient" if g >= 0 else f"Shortage of {abs(g)}"
    )
    return merged[["Type", "In Stock", "Predicted Need", "Gap", "Status"]]


# ─── Procurement Suggestions ──────────────────────────────────────────────────

def smart_predict_requirements(
    conn:        sqlite3.Connection,
    new_joiners: int,
    department:  str       = "",
    categories:  list[str] = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Department- and category-aware prediction.

    Returns:
        (breakdown_df, context_dict)
        breakdown_df  — per-type predicted needs (filtered by category if given)
        context_dict  — rich data passed to the LLM for reasoning:
                        current stock, dept distribution, OS/RAM/storage breakdowns
    """
    categories = categories or []

    # ── Base filter: assigned devices only ──
    base_where = "LOWER(is_assigned) = 'true' AND type != ''"

    # ── Department filter (maps to designation or source_sheet) ──
    dept_clause = ""
    dept_params: list = []
    if department.strip():
        dept_clause = (
            " AND (LOWER(designation) LIKE LOWER(?)"
            "   OR LOWER(source_sheet) LIKE LOWER(?))"
        )
        like = f"%{department.strip()}%"
        dept_params = [like, like]

    # ── Category filter ──
    cat_clause = ""
    cat_params: list = []
    if categories:
        placeholders = ",".join("?" * len(categories))
        cat_clause   = f" AND LOWER(type) IN ({placeholders})"
        cat_params   = [c.lower() for c in categories]

    full_where  = base_where + dept_clause + cat_clause
    all_params  = dept_params + cat_params

    # ── Device-type distribution ──
    dist = pd.read_sql_query(
        f"SELECT type, COUNT(*) AS cnt FROM {TABLE} "
        f"WHERE {full_where} GROUP BY type",
        conn,
        params=all_params,
    )

    if dist.empty or new_joiners <= 0:
        return pd.DataFrame(columns=["Type", "Predicted Need"]), {}

    total           = dist["cnt"].sum()
    dist["ratio"]   = dist["cnt"] / total
    dist["Predicted Need"] = (dist["ratio"] * new_joiners).round().astype(int)
    breakdown = dist.rename(columns={"type": "Type"})[["Type", "Predicted Need"]]
    breakdown = breakdown[breakdown["Predicted Need"] > 0].reset_index(drop=True)

    # ── Context for LLM ──

    # Stock levels per type
    stock = pd.read_sql_query(
        f"SELECT type, COUNT(*) AS in_stock FROM {TABLE} "
        f"WHERE LOWER(current_user) LIKE '%it stock%' AND type != '' GROUP BY type",
        conn,
    )
    stock_map = dict(zip(stock["type"], stock["in_stock"])) if not stock.empty else {}

    # OS breakdown (filtered)
    os_dist = pd.read_sql_query(
        f"SELECT os, COUNT(*) AS cnt FROM {TABLE} "
        f"WHERE {full_where} AND os != '' GROUP BY os ORDER BY cnt DESC",
        conn,
        params=all_params,
    )

    # RAM breakdown (filtered)
    ram_dist = pd.read_sql_query(
        f"SELECT ram, COUNT(*) AS cnt FROM {TABLE} "
        f"WHERE {full_where} AND ram != '' GROUP BY ram ORDER BY cnt DESC LIMIT 5",
        conn,
        params=all_params,
    )

    # Make/model top choices (filtered)
    top_models = pd.read_sql_query(
        f"SELECT make, model, COUNT(*) AS cnt FROM {TABLE} "
        f"WHERE {full_where} AND make != '' AND model != '' "
        f"GROUP BY make, model ORDER BY cnt DESC LIMIT 5",
        conn,
        params=all_params,
    )

    # Total assigned in dept/category scope
    total_scoped = int(conn.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE {full_where}",
        all_params,
    ).fetchone()[0])

    context = {
        "department":       department.strip() or "all departments",
        "categories":       categories or ["all"],
        "total_assigned":   total_scoped,
        "stock_by_type":    stock_map,
        "os_breakdown":     os_dist.to_dict(orient="records") if not os_dist.empty else [],
        "ram_breakdown":    ram_dist.to_dict(orient="records") if not ram_dist.empty else [],
        "top_models":       top_models.to_dict(orient="records") if not top_models.empty else [],
        "breakdown":        breakdown.to_dict(orient="records"),
    }

    return breakdown, context


def procurement_suggestions(conn: sqlite3.Connection, new_joiners: int) -> pd.DataFrame:
    gap_df = gap_analysis(conn, new_joiners)
    if gap_df.empty:
        return pd.DataFrame()

    shortage_types = gap_df[gap_df["Gap"] < 0][["Type", "Gap"]].copy()
    if shortage_types.empty:
        return pd.DataFrame(
            [{"Message": "Current stock is sufficient. No procurement needed."}]
        )

    rows = []
    for _, row in shortage_types.iterrows():
        device_type = row["Type"]
        qty_needed  = abs(int(row["Gap"]))

        top_model = pd.read_sql_query(
            f"""
            SELECT make, model, COUNT(*) AS usage_count
            FROM   {TABLE}
            WHERE  LOWER(type) = LOWER(?)
              AND  LOWER(is_assigned) = 'true'
              AND  model != ''
              AND  make  != ''
            GROUP  BY make, model
            ORDER  BY usage_count DESC
            LIMIT  1
            """,
            conn,
            params=(device_type,),
        )

        rows.append({
            "Type":               device_type,
            "Recommended Model":  top_model.iloc[0]["model"] if not top_model.empty else "Any",
            "Make":               top_model.iloc[0]["make"]  if not top_model.empty else "Any",
            "Qty to Procure":     qty_needed,
            "Reason":             f"Gap of {qty_needed} based on {new_joiners} new joiners",
        })

    return pd.DataFrame(rows)