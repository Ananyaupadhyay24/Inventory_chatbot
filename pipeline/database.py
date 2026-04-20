"""
pipeline/database.py
--------------------
Converts master_inventory.csv → SQLite database.

Responsibilities:
  - setup_database() : load CSV, create table, add indexes
  - get_schema()     : return LLM-readable schema + sample values
  - execute_query()  : run a SQL string and return a DataFrame
"""

import os
import sqlite3
import pandas as pd

TABLE = "inventory"


# ─── Setup ────────────────────────────────────────────────────────────────────

def setup_database(csv_path: str, db_path: str) -> sqlite3.Connection:
    """
    Create / refresh the SQLite database from the CSV.

    - Skips re-creation if row count already matches.
    - Creates indexes on the most-queried columns for speed.
    - Returns an open sqlite3 connection (check_same_thread=False for Streamlit).
    """
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    conn = sqlite3.connect(db_path, check_same_thread=False)

    # Check if already loaded and up-to-date
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        if count == len(df):
            print(f"[database] SQLite already has {count} records. Skipping re-creation.")
            return conn
    except Exception:
        pass  # Table doesn't exist yet

    # Create / replace table
    conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
    df.to_sql(TABLE, conn, if_exists="replace", index=False)

    # Indexes for frequently queried columns
    for col in [
        "current_user", "employee_code", "serial_no",
        "type", "os", "make", "source_sheet", "host_name",
    ]:
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{col} ON {TABLE}({col})"
        )

    conn.commit()
    print(f"[database] SQLite ready: {len(df)} rows in '{TABLE}' table at {db_path}")
    return conn


# ─── Query execution ──────────────────────────────────────────────────────────

def execute_query(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    """Run a SELECT query and return a DataFrame. Raises on error."""
    return pd.read_sql_query(sql, conn)


# ─── Schema for LLM ──────────────────────────────────────────────────────────

def get_schema(conn: sqlite3.Connection) -> str:
    """
    Build a compact schema string to include in the SQL generation prompt.
    Includes column names and representative sample values for key fields.
    """
    # Column list
    cursor = conn.execute(f"PRAGMA table_info({TABLE})")
    columns = [row[1] for row in cursor.fetchall()]

    # Sample distinct values for key columns
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

    # Row count
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


# ─── Asset Release (Employee Exit) ───────────────────────────────────────────

def release_assets(
    conn:         sqlite3.Connection,
    identifier:   str,
    new_location: str = "IT Stock",
) -> pd.DataFrame:
    """
    On employee exit: move all their assigned devices to IT Stock.

    Steps:
      1. Find all devices currently assigned to the employee.
      2. Copy current_user → old_user (preserve history).
      3. Set current_user = "IT Stock [location]" and is_assigned = "False".

    Args:
        conn:         Open SQLite connection.
        identifier:   Employee name or employee code (partial match allowed).
        new_location: Stock location label, e.g. "GGN", "Noida", "CHD".

    Returns:
        DataFrame of all released devices (before update).
    """
    safe_id = identifier.replace("'", "''")   # basic SQL injection guard

    devices = pd.read_sql_query(
        f"""
        SELECT rowid, *
        FROM   {TABLE}
        WHERE  (LOWER(current_user)  LIKE LOWER('%{safe_id}%')
             OR LOWER(employee_code) LIKE LOWER('%{safe_id}%'))
          AND  LOWER(is_assigned) = 'true'
        """,
        conn,
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
    """
    Current unassigned devices grouped by type, make, and location.
    """
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
    conn:          sqlite3.Connection,
    new_joiners:   int,
) -> pd.DataFrame:
    """
    Predict how many devices of each type will be needed for new_joiners.

    Logic:
      - Observe current assigned device type ratios per employee.
      - Scale that ratio to the expected headcount increase.

    Returns a DataFrame with columns: type, predicted_need.
    """
    # Current assigned device type distribution
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

    total      = dist["cnt"].sum()
    dist["ratio"] = dist["cnt"] / total
    dist["Predicted Need"] = (dist["ratio"] * new_joiners).round().astype(int)
    dist = dist.rename(columns={"type": "Type"})[["Type", "Predicted Need"]]
    dist = dist[dist["Predicted Need"] > 0]
    return dist.reset_index(drop=True)


# ─── Gap Analysis ─────────────────────────────────────────────────────────────

def gap_analysis(
    conn:        sqlite3.Connection,
    new_joiners: int,
) -> pd.DataFrame:
    """
    Compare current IT Stock vs predicted device requirement for new_joiners.

    Returns a DataFrame with columns:
        Type | In Stock | Predicted Need | Gap | Status
    """
    # Current stock per type
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
        stock.rename(columns={"type": "Type"}),
        on="Type",
        how="left",
    ).fillna(0)

    merged["In Stock"]       = merged["in_stock"].astype(int)
    merged["Predicted Need"] = merged["Predicted Need"].astype(int)
    merged["Gap"]            = merged["In Stock"] - merged["Predicted Need"]
    merged["Status"]         = merged["Gap"].apply(
        lambda g: "Sufficient" if g >= 0 else f"Shortage of {abs(g)}"
    )

    return merged[["Type", "In Stock", "Predicted Need", "Gap", "Status"]]


# ─── Procurement Suggestions ──────────────────────────────────────────────────

def procurement_suggestions(
    conn:        sqlite3.Connection,
    new_joiners: int,
) -> pd.DataFrame:
    """
    Based on the gap analysis, suggest which models to procure and how many.

    Logic:
      - Find the most commonly assigned models for each device type.
      - If a gap exists, suggest procuring those models.

    Returns a DataFrame with columns:
        Type | Recommended Model | Make | Qty to Procure | Reason
    """
    gap_df = gap_analysis(conn, new_joiners)
    if gap_df.empty:
        return pd.DataFrame()

    shortage_types = gap_df[gap_df["Gap"] < 0][["Type", "Gap"]].copy()
    if shortage_types.empty:
        return pd.DataFrame(
            [{"Message": "Current stock is sufficient for the expected headcount. No procurement needed."}]
        )

    rows = []
    for _, row in shortage_types.iterrows():
        device_type = row["Type"]
        qty_needed  = abs(int(row["Gap"]))

        # Most assigned make+model for this type
        top_model = pd.read_sql_query(
            f"""
            SELECT make, model, COUNT(*) AS usage_count
            FROM   {TABLE}
            WHERE  LOWER(type) = LOWER('{device_type}')
              AND  LOWER(is_assigned) = 'true'
              AND  model != ''
              AND  make  != ''
            GROUP  BY make, model
            ORDER  BY usage_count DESC
            LIMIT  1
            """,
            conn,
        )

        if not top_model.empty:
            rows.append({
                "Type":               device_type,
                "Recommended Model":  top_model.iloc[0]["model"],
                "Make":               top_model.iloc[0]["make"],
                "Qty to Procure":     qty_needed,
                "Reason":             f"Gap of {qty_needed} based on {new_joiners} new joiners",
            })
        else:
            rows.append({
                "Type":               device_type,
                "Recommended Model":  "Any",
                "Make":               "Any",
                "Qty to Procure":     qty_needed,
                "Reason":             f"Gap of {qty_needed} based on {new_joiners} new joiners",
            })

    return pd.DataFrame(rows)
