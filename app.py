"""
app.py
------
IT Admin Inventory Chatbot — Streamlit Frontend
Calls the FastAPI backend at http://localhost:8000

Run backend first : uvicorn backend.main:app --reload --port 8000
Run frontend      : streamlit run app.py
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

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT  = 120   # seconds (LangGraph agent can take a moment)

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _auth_headers() -> dict:
    token = st.session_state.get("access_token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def do_login(username: str, password: str) -> bool:
    """POST /auth/login → store tokens in session_state."""
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
    """Exchange refresh token for a new access token silently."""
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


def render_login_page():
    """Full-page login form. Calls st.stop() until authenticated."""
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("## IT Admin Login")
        st.markdown("---")
        with st.form("login_form"):
            username  = st.text_input("Username", placeholder="admin")
            password  = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            if do_login(username, password):
                st.rerun()
            else:
                st.error("Invalid username or password.")
        st.caption("Default: **admin** / admin123   ·   **viewer** / viewer123")
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
        # ── User info + logout ──
        username = st.session_state.get("username", "")
        role     = st.session_state.get("role", "viewer")
        st.markdown(f"**{username}** `{role}`")
        if st.button("Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        st.divider()

        st.header("Live Dashboard")

        c1, c2 = st.columns(2)
        c1.metric("Total Assets", stats.get("total",    0))
        c2.metric("In Stock",     stats.get("in_stock", 0))
        c1.metric("Laptops",      stats.get("laptops",  0))
        c2.metric("Desktops",     stats.get("desktops", 0))
        c1.metric("Faulty",       stats.get("faulty",   0))
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
    st.caption("LangGraph · SQL Agent · ChromaDB semantic fallback · GPT-4o-mini")

    if "messages"    not in st.session_state:
        st.session_state["messages"]    = []
    if "llm_history" not in st.session_state:
        st.session_state["llm_history"] = []

    for i, msg in enumerate(st.session_state["messages"]):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
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
        st.session_state["llm_history"].append({"role": "user", "content": user_input})

        with st.chat_message("assistant"):
            with st.spinner("Running SQL agent..."):
                resp = api_post("/chat", {
                    "query":   user_input,
                    "history": st.session_state["llm_history"],
                })

            answer  = resp.get("answer",  "No answer returned.")
            records = resp.get("records", [])
            count   = resp.get("count",   0)

            st.markdown(answer)
            msg_idx = len(st.session_state["messages"])

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
            "role": "assistant", "content": answer, "table": records,
        })
        st.session_state["llm_history"].append({
            "role": "assistant", "content": answer,
        })


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


# ─── Tab 3: Analytics ────────────────────────────────────────────────────────
def render_analytics_tab():
    st.subheader("Analytics — Stock, Prediction & Procurement")

    # ── A: Current Stock ──────────────────────────────────────────────────────
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

    # ── B: Prediction ─────────────────────────────────────────────────────────
    with st.expander("Future Requirement Prediction", expanded=True):
        st.caption("Estimate device needs for upcoming hires based on current ratios.")
        joiners = st.number_input("Expected new joiners", min_value=1, max_value=500,
                                  value=10, step=1, key="pred_joiners")
        if st.button("Predict Requirements", key="btn_predict"):
            with st.spinner("Calculating..."):
                resp = api_post("/analytics/predict", {"new_joiners": int(joiners)})
            if resp.get("breakdown"):
                st.success(f"Device needs for **{joiners}** new joiners:")
                st.dataframe(pd.DataFrame(resp["breakdown"]), use_container_width=True)
            else:
                st.warning("Could not generate prediction.")

    st.divider()

    # ── C: Gap Analysis ───────────────────────────────────────────────────────
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

    # ── D: Procurement Suggestions ────────────────────────────────────────────
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


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    st.title("IT Admin — Inventory Assistant")
    st.caption("FastAPI · LangGraph · SQL Agent · ChromaDB · OpenAI GPT-4o-mini")

    # ── Auth gate: show login page if not authenticated ──
    if not st.session_state.get("access_token"):
        render_login_page()     # calls st.stop() — nothing below runs

    # Load stats from backend
    stats = api_get("/assets/stats") or {}

    render_sidebar(stats)

    tab_chat, tab_release, tab_analytics = st.tabs([
        "Chat",
        "Asset Release (Employee Exit)",
        "Analytics & Procurement",
    ])
    with tab_chat:
        render_chat_tab()
    with tab_release:
        render_release_tab()
    with tab_analytics:
        render_analytics_tab()


if __name__ == "__main__":
    main()
