"""
backend/routes/assets.py
------------------------
Asset lookup, release (employee exit), and stock endpoints.

Routes:
    GET  /assets/stats            — Dashboard KPIs
    GET  /assets/stock            — All unassigned devices
    POST /assets/release/preview  — Preview devices to release
    POST /assets/release/confirm  — Confirm & execute release
"""

import sqlite3

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from backend.models import (
    DashboardStats,
    ReleasePreviewRequest,
    ReleaseConfirmRequest,
    ReleaseResponse,
    StockSummaryResponse,
)
from backend.dependencies import get_db, get_current_user, require_admin
from pipeline.database    import release_assets, get_stock_summary

router = APIRouter(prefix="/assets", tags=["Assets"])


# ─── Dashboard stats (any authenticated user) ─────────────────────────────────

@router.get("/stats", response_model=DashboardStats)
def stats(
    conn:         sqlite3.Connection = Depends(get_db),
    current_user: dict               = Depends(get_current_user),
):
    """Return live KPI counts for the dashboard."""

    def count(sql: str, params: tuple = ()) -> int:
        return conn.execute(sql, params).fetchone()[0]

    total    = count("SELECT COUNT(*) FROM inventory")
    laptops  = count("SELECT COUNT(*) FROM inventory WHERE LOWER(type) = 'laptop'")
    desktops = count("SELECT COUNT(*) FROM inventory WHERE LOWER(type) = 'desktop'")
    mac_mini = count("SELECT COUNT(*) FROM inventory WHERE LOWER(type) = 'mac mini'")
    stock    = count("SELECT COUNT(*) FROM inventory WHERE LOWER(current_user) LIKE '%it stock%'")
    faulty   = count(
        "SELECT COUNT(*) FROM inventory "
        "WHERE LOWER(current_user) LIKE '%fault%' OR LOWER(source_sheet) LIKE '%fault%'"
    )
    win10    = count("SELECT COUNT(*) FROM inventory WHERE LOWER(os) LIKE '%windows 10%'")
    win11    = count("SELECT COUNT(*) FROM inventory WHERE LOWER(os) LIKE '%windows 11%'")
    linux    = count("SELECT COUNT(*) FROM inventory WHERE LOWER(os) = 'linux'")
    macos    = count("SELECT COUNT(*) FROM inventory WHERE LOWER(os) = 'macos'")
    miss_sn  = count("SELECT COUNT(*) FROM inventory WHERE serial_no = ''")

    # FIX: was only checking agreement_verified — must check BOTH fields to match
    # the definition used everywhere else in the codebase
    miss_agr = count(
        "SELECT COUNT(*) FROM inventory "
        "WHERE agreement_verified = '' AND agreement_doc = '' AND LOWER(type) = 'laptop'"
    )

    return DashboardStats(
        total=total, laptops=laptops, desktops=desktops, mac_mini=mac_mini,
        in_stock=stock, faulty=faulty,
        windows_10=win10, windows_11=win11, linux=linux, macos=macos,
        missing_serial=miss_sn, missing_agreement=miss_agr,
    )


# ─── Stock visibility ─────────────────────────────────────────────────────────

@router.get("/stock", response_model=StockSummaryResponse)
def stock_summary(
    conn:         sqlite3.Connection = Depends(get_db),
    current_user: dict               = Depends(get_current_user),
):
    """Return all unassigned devices grouped by type, make, and location."""
    df = get_stock_summary(conn)
    records = df.to_dict(orient="records") if not df.empty else []
    return StockSummaryResponse(records=records, total=sum(r.get("available_count", 0) for r in records))


# ─── Asset release — preview ──────────────────────────────────────────────────

@router.post("/release/preview")
def release_preview(
    body:         ReleasePreviewRequest,
    conn:         sqlite3.Connection = Depends(get_db),
    current_user: dict               = Depends(get_current_user),
):
    """
    Preview which devices will be released for a given employee.
    Does NOT modify the database.
    """
    identifier = body.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Identifier must not be empty.")

    # FIX: parameterized query — previous f-string approach was SQL-injectable
    like_pattern = f"%{identifier}%"
    df = pd.read_sql_query(
        """
        SELECT current_user, employee_code, type, make, model,
               serial_no, host_name, ram, os, source_sheet
        FROM   inventory
        WHERE  (LOWER(current_user)  LIKE LOWER(?)
             OR LOWER(employee_code) LIKE LOWER(?))
          AND  LOWER(is_assigned) = 'true'
        """,
        conn,
        params=(like_pattern, like_pattern),
    )

    return {
        "identifier":   identifier,
        "device_count": len(df),
        "devices":      df.to_dict(orient="records"),
    }


# ─── Asset release — confirm ──────────────────────────────────────────────────

@router.post("/release/confirm", response_model=ReleaseResponse)
def release_confirm(
    body:         ReleaseConfirmRequest,
    conn:         sqlite3.Connection = Depends(get_db),
    current_user: dict               = Depends(require_admin),      # ← admin only
):
    """
    Execute the asset release:
      - Moves all assigned devices to IT Stock.
      - Preserves previous user in old_user field.
    """
    if not body.identifier.strip():
        raise HTTPException(status_code=400, detail="Identifier must not be empty.")

    released = release_assets(
        conn=conn,
        identifier=body.identifier.strip(),
        new_location=body.new_location.strip(),
    )

    if released.empty:
        return ReleaseResponse(
            released_count=0,
            devices=[],
            message=f"No assigned devices found for '{body.identifier}'.",
        )

    return ReleaseResponse(
        released_count=len(released),
        devices=released.to_dict(orient="records"),
        message=(
            f"{len(released)} device(s) moved to "
            f"'IT Stock {body.new_location}' successfully."
        ),
    )