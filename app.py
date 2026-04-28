"""
app.py
------
IT Admin Inventory Chatbot — Streamlit Frontend
Calls the FastAPI backend at http://localhost:8000

Run backend first : uvicorn backend.main:app --reload --port 8000
Run frontend      : streamlit run app.py

FIXES APPLIED
-------------
  BUG-11 : llm_history is capped at the last 20 messages before sending to
           the backend, preventing payload bloat and LLM context overflow.
  NEW    : Query Debug panel (admin only) shows: query type, entities,
           SQL generated, rows returned, confidence, path taken.
  NEW    : Stage status indicator during query execution.
  NEW    : Audit Log tab (admin only) shows recent queries.
  NEW    : Logout calls /auth/logout to invalidate the refresh token.
"""

import os

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="IT Admin — Inventory Assistant",
    page_icon="🖥️",
    layout="wide",
)

API_BASE           = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT            = 120
MAX_HISTORY_ITEMS  = 20   # BUG-11 fix: cap history before sending


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _auth_headers() -> dict:
    token = st.session_state.get("access_token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def do_login(username: str, password: str) -> bool:
    try:
        r = httpx.post(
            f"{API_BASE}/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            st.session_state["access_token"]  = data["access_token"]
            st.session_state["refresh_token"] = data["refresh_token"]
            st.session_state["username"]      = username
            st.session_state["role"]          = data.get("role", "viewer")
            return True
        return False
    except httpx.ConnectError:
        st.error("Cannot reach the backend. Run:\n`uvicorn backend.main:app --reload --port 8000`")
        st.stop()


def try_refresh() -> bool:
    rt = st.session_state.get("refresh_token", "")
    if not rt:
        return False
    try:
        r = httpx.post(f"{API_BASE}/auth/refresh", json={"refresh_token": rt}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            st.session_state["access_token"]  = data["access_token"]
            st.session_state["refresh_token"] = data["refresh_token"]
            return True
    except Exception:
        pass
    return False


def do_logout():
    """Call /auth/logout to revoke refresh token, then clear session."""
    try:
        httpx.post(f"{API_BASE}/auth/logout", headers=_auth_headers(), timeout=5)
    except Exception:
        pass
    st.session_state.clear()


def render_login_page():
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("## 🖥️ IT Admin Login")
        st.markdown("---")
        with st.form("login_form"):
            username  = st.text_input("Username", placeholder="Enter username")
            password  = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            if do_login(username, password):
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()


# ─── API helpers ──────────────────────────────────────────────────────────────

def api_get(path: str) -> dict:
    try:
        r = httpx.get(f"{API_BASE}{path}", headers=_auth_headers(), timeout=TIMEOUT)
        if r.status_code == 401:
            if try_refresh():
                r = httpx.get(f"{API_BASE}{path}", headers=_auth_headers(), timeout=TIMEOUT)
            else:
                st.session_state.clear()
                st.rerun()
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        st.error("Cannot reach the backend. Run: `uvicorn backend.main:app --reload --port 8000`")
        st.stop()
    except httpx.HTTPStatusError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
        return {}


def api_post(path: str, body: dict) -> dict:
    try:
        r = httpx.post(f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=TIMEOUT)
        if r.status_code == 401:
            if try_refresh():
                r = httpx.post(f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=TIMEOUT)
            else:
                st.session_state.clear()
                st.rerun()
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        st.error("Cannot reach the backend. Run: `uvicorn backend.main:app --reload --port 8000`")
        st.stop()
    except httpx.HTTPStatusError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
        return {}


# ─── Quick query groups ────────────────────────────────────────────────────────

QUERY_GROUPS = {
    "Asset Lookup": [
        "What machine does Anjali Garg have?",
        "Show details for employee NTZ2186",
        "Who is using host NTZ-LAP-045?",
        "Find serial number PG02JT3N",
        "Which assets are under PO PORD/00217?",
    ],
    "Stock & Faults": [
        "Show all machines currently in IT Stock",
        "What laptops are available in GGN stock?",
        "List all faulty or repair devices",
        "How many spare laptops are available?",
    ],
    "OS & Hardware Audit": [
        "Which machines still run Windows 10?",
        "Show all machines on OS build 21H2",
        "List all Linux machines and their users",
        "Show machines with less than 16GB RAM",
        "List all Lenovo E14 laptops",
        "How many Dell vs Lenovo devices?",
    ],
    "Compliance": [
        "Which laptops are missing an agreement?",
        "Show all verified laptop agreements",
        "How many laptops have no agreement document?",
    ],
    "Data Health": [
        "Show the full data health report",
        "Are there any duplicate serial numbers?",
        "Which records have missing serial numbers?",
        "Assets with no PO number recorded",
    ],
    "Reports": [
        "Give me the full inventory summary",
        "Asset count broken down by location",
        "Device breakdown by manufacturer",
        "Show all EOL devices still assigned to users",
        "Machines transferred from a previous user",
        "List all Junior Software Engineers and their machines",
    ],
}


# ─── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar(stats: dict):
    with st.sidebar:
        username = st.session_state.get("username", "")
        role     = st.session_state.get("role", "viewer")
        st.markdown(f"**{username}** `{role}`")

        # BUG-08 fix: logout calls /auth/logout to invalidate refresh token
        if st.button("Logout", use_container_width=True):
            do_logout()
            st.rerun()
        st.divider()

        st.header("Live Dashboard")
        c1, c2 = st.columns(2)
        c1.metric("Total Assets", stats.get("total",      0))
        c2.metric("In Stock",     stats.get("in_stock",   0))
        c1.metric("Laptops",      stats.get("laptops",    0))
        c2.metric("Desktops",     stats.get("desktops",   0))
        c1.metric("Faulty",       stats.get("faulty",     0))
        c2.metric("Win10",        stats.get("windows_10", 0))

        st.divider()
        st.subheader("Needs Attention")
        if stats.get("missing_agreement", 0):
            st.warning(f"{stats['missing_agreement']} laptops missing agreement")
        if stats.get("windows_10", 0):
            st.warning(f"{stats['windows_10']} machines need OS upgrade")
        if stats.get("missing_serial", 0):
            st.warning(f"{stats['missing_serial']} records missing serial no.")
        if stats.get("faulty", 0):
            st.info(f"{stats['faulty']} devices in faulty / repair state")

        st.divider()
        st.subheader("Pipeline Status")
        health = api_get("/health")
        if health.get("status") == "ok":
            st.success(f"API online · {health.get('chroma_indexed', 0)} vectors indexed")
            if not health.get("rate_limiting"):
                st.caption("⚠️ Rate limiting inactive (install slowapi)")
        else:
            st.error("API offline")

        st.divider()
        st.subheader("Quick Queries")
        for group, queries in QUERY_GROUPS.items():
            with st.expander(group):
                for q in queries:
                    if st.button(q, use_container_width=True, key=f"btn_{q}"):
                        st.session_state["pending_query"] = q
                        st.rerun()

        st.divider()
        if st.button("Clear chat", use_container_width=True):
            st.session_state["messages"]    = []
            st.session_state["llm_history"] = []
            st.rerun()


# ─── Tab 1: Chat ──────────────────────────────────────────────────────────────

def render_chat_tab():
    st.subheader("Ask anything about your IT assets")
    st.caption("LangGraph · SQL Agent · ChromaDB semantic fallback · Groq llama-3.3-70b")

    role = st.session_state.get("role", "viewer")

    # Admin-only: Query Debug toggle
    show_debug = False
    if role == "admin":
        show_debug = st.toggle(
            "🔍 Query Debug (admin)",
            value=False,
            help="Shows SQL generated, entities extracted, path taken, and confidence for each query.",
        )

    if "messages"    not in st.session_state:
        st.session_state["messages"]    = []
    if "llm_history" not in st.session_state:
        st.session_state["llm_history"] = []

    # Render message history
    for i, msg in enumerate(st.session_state["messages"]):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Show debug info for assistant messages if debug is on
            if show_debug and msg["role"] == "assistant" and msg.get("debug"):
                dbg = msg["debug"]
                with st.expander("🔍 Debug info", expanded=False):
                    d1, d2, d3, d4 = st.columns(4)
                    d1.markdown(f"**Query type**\n\n`{dbg.get('query_type', '—')}`")
                    d2.markdown(f"**Confidence**\n\n`{dbg.get('confidence', '—')}`")
                    d3.markdown(f"**Rows returned**\n\n`{dbg.get('count', 0)}`")
                    d4.markdown(f"**Path**\n\n`{dbg.get('path', '—')}`")
                    if dbg.get("sql"):
                        st.code(dbg["sql"], language="sql")

            if "table" in msg and msg["table"]:
                df = pd.DataFrame(msg["table"])
                st.dataframe(df, use_container_width=True)
                st.download_button(
                    "Download CSV",
                    data=df.to_csv(index=False).encode(),
                    file_name=f"export_{i}.csv",
                    mime="text/csv",
                    key=f"dl_{i}",
                )

    user_input = st.chat_input("Ask about any asset, employee, OS, hardware, or compliance...")
    if "pending_query" in st.session_state:
        user_input = st.session_state.pop("pending_query")

    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)
        st.session_state["messages"].append({"role": "user", "content": user_input})
        # BUG-11 fix: only keep last MAX_HISTORY_ITEMS entries in llm_history
        st.session_state["llm_history"].append({"role": "user", "content": user_input})
        st.session_state["llm_history"] = st.session_state["llm_history"][-MAX_HISTORY_ITEMS:]

        with st.chat_message("assistant"):
            # Stage status indicator — shows progress while the agent is running
            status_placeholder = st.empty()
            stages = [
                "🔍 Classifying query...",
                "🧩 Extracting entities...",
                "✍️  Generating SQL...",
                "⚙️  Executing query...",
                "📝 Writing answer...",
            ]

            import time
            import threading

            stage_idx   = [0]
            stop_flag   = [False]
            status_text = status_placeholder.status(stages[0], expanded=False)

            def cycle_stages():
                i = 0
                while not stop_flag[0]:
                    status_placeholder.status(stages[i % len(stages)], expanded=False)
                    time.sleep(1.8)
                    i += 1

            t = threading.Thread(target=cycle_stages, daemon=True)
            t.start()

            # BUG-11 fix: cap history sent to backend
            history_to_send = st.session_state["llm_history"][-MAX_HISTORY_ITEMS:]

            resp = api_post("/chat", {
                "query":   user_input,
                "history": history_to_send,
            })

            stop_flag[0] = True
            status_placeholder.empty()

            answer  = resp.get("answer",  "No answer returned.")
            records = resp.get("records", [])
            count   = resp.get("count",   0)

            st.markdown(answer)
            msg_idx = len(st.session_state["messages"])

            debug_info = None
            if show_debug and resp:
                # The backend doesn't expose these fields yet in ChatResponse,
                # but they are logged in audit_log. For now we surface what we have.
                debug_info = {
                    "count":      count,
                    "query_type": resp.get("query_type", "—"),
                    "confidence": resp.get("confidence", "—"),
                    "sql":        resp.get("sql_generated", ""),
                    "path":       resp.get("path_taken", "—"),
                }
                if any(v and v != "—" and v != "" for v in debug_info.values()):
                    with st.expander("🔍 Debug info", expanded=True):
                        d1, d2, d3 = st.columns(3)
                        d1.markdown(f"**Confidence**\n\n`{debug_info.get('confidence', '—')}`")
                        d2.markdown(f"**Rows returned**\n\n`{count}`")
                        d3.markdown(f"**Path**\n\n`{debug_info.get('path', '—')}`")
                        if debug_info.get("sql"):
                            st.code(debug_info["sql"], language="sql")

            if records:
                df = pd.DataFrame(records)
                st.dataframe(df, use_container_width=True)
                st.caption(f"{count} record(s) found")
                st.download_button(
                    "Download CSV",
                    data=df.to_csv(index=False).encode(),
                    file_name="export.csv",
                    mime="text/csv",
                    key=f"dl_new_{msg_idx}",
                )

        st.session_state["messages"].append({
            "role": "assistant",
            "content": answer,
            "table":   records,
            "debug":   debug_info,
        })
        st.session_state["llm_history"].append({"role": "assistant", "content": answer})
        st.session_state["llm_history"] = st.session_state["llm_history"][-MAX_HISTORY_ITEMS:]


# ─── Tab 2: Asset Release ─────────────────────────────────────────────────────

def render_release_tab():
    st.subheader("Asset Release — Employee Exit")
    st.caption("Free all devices assigned to a departing employee and move them to IT Stock.")

    with st.form("release_form"):
        c1, c2 = st.columns(2)
        identifier   = c1.text_input("Employee Name or Code", placeholder="e.g. Anjali Garg or NTZ2076")
        new_location = c2.selectbox(
            "Move to Stock Location",
            ["GGN", "Noida", "CHD", "Mohali", "5th Floor", "6th Floor", "7th Floor"],
        )
        submitted = st.form_submit_button("Preview Devices to Release", use_container_width=True)

    if submitted and identifier.strip():
        with st.spinner("Looking up assigned devices..."):
            resp = api_post("/assets/release/preview", {"identifier": identifier.strip()})

        devices = resp.get("devices", [])
        count   = resp.get("device_count", 0)

        if not devices:
            st.warning(f"No assigned devices found for **{identifier}**.")
        else:
            st.info(f"Found **{count}** device(s) assigned to **{identifier}**:")
            st.dataframe(pd.DataFrame(devices), use_container_width=True)
            st.session_state["release_identifier"] = identifier.strip()
            st.session_state["release_location"]   = new_location
            st.session_state["release_preview"]    = devices

    if st.session_state.get("release_preview"):
        st.divider()
        st.warning(
            f"Confirm release of **{len(st.session_state['release_preview'])}** device(s) "
            f"from **{st.session_state['release_identifier']}** "
            f"→ **IT Stock {st.session_state['release_location']}**?"
        )
        c1, c2 = st.columns(2)
        if c1.button("Confirm Release", type="primary", use_container_width=True):
            with st.spinner("Releasing assets..."):
                resp = api_post("/assets/release/confirm", {
                    "identifier":   st.session_state["release_identifier"],
                    "new_location": st.session_state["release_location"],
                })
            st.success(resp.get("message", "Done."))
            if resp.get("devices"):
                st.dataframe(pd.DataFrame(resp["devices"]), use_container_width=True)
            for key in ("release_preview", "release_identifier", "release_location"):
                st.session_state.pop(key, None)

        if c2.button("Cancel", use_container_width=True):
            for key in ("release_preview", "release_identifier", "release_location"):
                st.session_state.pop(key, None)
            st.rerun()

    st.divider()
    st.markdown("#### Current IT Stock")
    with st.spinner("Loading stock..."):
        stock_resp = api_get("/assets/stock")
    stock = stock_resp.get("records", [])
    if stock:
        st.dataframe(pd.DataFrame(stock), use_container_width=True)
        st.caption(f"Total available: {stock_resp.get('total', 0)} units")
    else:
        st.info("No items currently in IT Stock.")


# ─── Tab 3: Analytics ─────────────────────────────────────────────────────────

def render_analytics_tab():
    st.subheader("Analytics — Stock, Prediction & Procurement")

    with st.expander("Current Stock Visibility", expanded=True):
        st.caption("All unassigned devices in IT Stock, grouped by type and location.")
        with st.spinner("Loading..."):
            resp  = api_get("/assets/stock")
        stock = resp.get("records", [])
        if stock:
            c1, c2 = st.columns([2, 1])
            c1.dataframe(pd.DataFrame(stock), use_container_width=True)
            type_df = pd.DataFrame(stock).groupby("type")["available_count"].sum().reset_index()
            c2.markdown("**By Type**")
            c2.dataframe(type_df, use_container_width=True)
            st.download_button("Download", pd.DataFrame(stock).to_csv(index=False).encode(),
                               "current_stock.csv", "text/csv")
        else:
            st.info("No devices in IT Stock currently.")

    st.divider()

    with st.expander("Future Requirement Prediction", expanded=True):
        st.caption(
            "Estimate device needs for upcoming hires. "
            "Filter by department and device category for an AI-reasoned forecast."
        )

        c1, c2, c3 = st.columns([1, 1.2, 1.5])

        joiners = c1.number_input(
            "Expected new joiners",
            min_value=1, max_value=500, value=10, step=1,
            key="pred_joiners",
        )

        department = c2.text_input(
            "Department / Team  (optional)",
            placeholder="e.g. Engineering, QA, Design",
            key="pred_dept",
            help="Matches against designation and office location. Leave blank for company-wide.",
        )

        categories = c3.multiselect(
            "Device category  (optional)",
            options=["Laptop", "Desktop", "MAC Mini"],
            default=[],
            key="pred_cats",
            help="Leave blank to include all device types.",
        )

        if st.button("Predict Requirements", key="btn_predict"):
            with st.spinner("Calculating and generating AI insights…"):
                resp = api_post("/analytics/smart-predict", {
                    "new_joiners": int(joiners),
                    "department":  department.strip(),
                    "categories":  categories,
                })

            if resp.get("breakdown"):
                scope_label = resp.get("department", "All Departments")
                cats_label  = ", ".join(resp.get("categories") or ["All"])
                st.success(
                    f"Device forecast for **{joiners}** new joiner(s) · "
                    f"Dept: **{scope_label}** · Category: **{cats_label}**"
                )

                st.dataframe(
                    pd.DataFrame(resp["breakdown"]),
                    use_container_width=True,
                )

                # ── AI Reasoning ──────────────────────────────────────────────
                st.markdown("#### 🤖 AI Analysis")

                col_r, col_a = st.columns(2)

                with col_r:
                    st.markdown("**What's needed & why**")
                    st.info(resp.get("reasoning", "—"))

                with col_a:
                    st.markdown("**Recommended advancements**")
                    st.success(resp.get("advancements", "—"))

            else:
                st.warning(
                    "Could not generate a prediction for those filters. "
                    "Try a broader department name or clear the category filter."
                )

    st.divider()

    with st.expander("Stock vs Requirement Gap Analysis", expanded=True):
        st.caption("Compare current IT Stock against predicted requirements.")
        joiners_gap = st.number_input("Expected new joiners", min_value=1, max_value=500,
                                      value=10, step=1, key="gap_joiners")
        if st.button("Run Gap Analysis", key="btn_gap"):
            with st.spinner("Analysing..."):
                resp = api_post("/analytics/gap", {"new_joiners": int(joiners_gap)})
            if resp.get("breakdown"):
                df = pd.DataFrame(resp["breakdown"])

                def highlight_gap(row):
                    color = "#d4edda" if row["Gap"] >= 0 else "#f8d7da"
                    return [f"background-color: {color}"] * len(row)

                st.dataframe(df.style.apply(highlight_gap, axis=1), use_container_width=True)
                if resp.get("has_shortage"):
                    st.error(f"Shortage in: {', '.join(resp['shortage_types'])}")
                else:
                    st.success("Current stock is sufficient.")
                st.download_button("Download", df.to_csv(index=False).encode(),
                                   "gap_analysis.csv", "text/csv")
            else:
                st.warning("Could not run gap analysis.")

    st.divider()

    with st.expander("Procurement Suggestions", expanded=True):
        st.caption("Recommended models and quantities to procure based on the gap.")
        joiners_proc = st.number_input("Expected new joiners", min_value=1, max_value=500,
                                       value=10, step=1, key="proc_joiners")
        if st.button("Generate Procurement Suggestions", key="btn_proc"):
            with st.spinner("Generating..."):
                resp = api_post("/analytics/procurement", {"new_joiners": int(joiners_proc)})
            if resp.get("sufficient"):
                st.success("Current stock is sufficient. No procurement needed.")
            elif resp.get("suggestions"):
                df = pd.DataFrame(resp["suggestions"])
                st.dataframe(df, use_container_width=True)
                st.info(f"Total units to procure: **{resp.get('total_units', 0)}**")
                st.download_button("Download", df.to_csv(index=False).encode(),
                                   "procurement.csv", "text/csv")
            else:
                st.warning("Could not generate suggestions.")


# ─── Tab 4: Audit Log (admin only) ───────────────────────────────────────────

def render_audit_tab():
    st.subheader("Audit Log")
    st.caption("Recent queries, SQL generated, and confidence levels (admin only).")

    col1, col2 = st.columns([1, 4])
    limit = col1.number_input("Entries to load", min_value=10, max_value=500, value=50, step=10)

    if col2.button("Refresh", use_container_width=False):
        st.session_state.pop("audit_data", None)

    if "audit_data" not in st.session_state:
        with st.spinner("Loading audit log..."):
            resp = api_get(f"/admin/audit-log?limit={limit}")
        st.session_state["audit_data"] = resp

    resp = st.session_state.get("audit_data", {})

    if not resp or not resp.get("entries"):
        st.info("No audit log entries found.")
        return

    df = pd.DataFrame(resp["entries"])
    st.caption(f"Showing {resp.get('count', 0)} entries")

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Queries",    len(df))
    m2.metric("High Confidence",  int((df["confidence"] == "high").sum())   if "confidence" in df.columns else "—")
    m3.metric("Low Confidence",   int((df["confidence"] == "low").sum())    if "confidence" in df.columns else "—")
    m4.metric("0-row Results",    int(df["row_count"].astype(int).eq(0).sum()) if "row_count" in df.columns else "—")

    st.divider()

    # Colour-code confidence
    def highlight_confidence(row):
        c = row.get("confidence", "")
        if c == "high":
            return ["background-color: #d4edda"] * len(row)
        if c == "medium":
            return ["background-color: #fff3cd"] * len(row)
        if c == "low":
            return ["background-color: #f8d7da"] * len(row)
        return [""] * len(row)

    display_cols = [
        c for c in ["timestamp", "username", "user_role", "original_query",
                     "query_type", "row_count", "confidence", "path_taken",
                     "sql_generated", "answer_preview"]
        if c in df.columns
    ]
    styled = df[display_cols].style.apply(highlight_confidence, axis=1)
    st.dataframe(styled, use_container_width=True, height=500)

    st.download_button(
        "Download Audit Log CSV",
        data=df[display_cols].to_csv(index=False).encode(),
        file_name="audit_log.csv",
        mime="text/csv",
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    st.title("🖥️ IT Admin — Inventory Assistant")
    st.caption("FastAPI · LangGraph · SQL Agent · ChromaDB · Groq llama-3.3-70b")

    if not st.session_state.get("access_token"):
        render_login_page()

    stats = api_get("/assets/stats") or {}
    render_sidebar(stats)

    role = st.session_state.get("role", "viewer")

    # Admins get the Audit Log tab; viewers don't
    if role == "admin":
        tab_chat, tab_release, tab_analytics, tab_audit = st.tabs([
            "💬 Chat",
            "📤 Asset Release (Employee Exit)",
            "📊 Analytics & Procurement",
            "📋 Audit Log",
        ])
        with tab_audit:
            render_audit_tab()
    else:
        tab_chat, tab_release, tab_analytics = st.tabs([
            "💬 Chat",
            "📤 Asset Release (Employee Exit)",
            "📊 Analytics & Procurement",
        ])

    with tab_chat:
        render_chat_tab()
    with tab_release:
        render_release_tab()
    with tab_analytics:
        render_analytics_tab()


if __name__ == "__main__":
    main()