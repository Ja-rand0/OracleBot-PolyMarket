"""OracleBot — Streamlit Web Dashboard (entry point)."""
from __future__ import annotations

import sys
import os

# Ensure project root is on sys.path so `import config` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from streamlit_autorefresh import st_autorefresh

import config
from gui.db_queries import get_db_stats, get_db_file_size

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="OracleBot",
    page_icon=":crystal_ball:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## :crystal_ball: OracleBot")
    st.caption("Sharp money detection dashboard")
    st.divider()

    # Auto-refresh toggle
    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_interval = st.select_slider(
        "Interval (seconds)",
        options=[15, 30, 60, 120, 300],
        value=60,
        disabled=not auto_refresh,
    )

    if auto_refresh:
        st_autorefresh(interval=refresh_interval * 1000, key="auto_refresh")

    st.divider()

    # DB info
    stats = get_db_stats()
    db_size = get_db_file_size()
    st.markdown("**Database**")
    st.caption(f"Path: `{config.DB_PATH}`")
    st.caption(f"Size: {db_size:.1f} MB")
    st.caption(f"Markets: {stats['total_markets']:,}")
    st.caption(f"Trades: {stats['total_bets']:,}")
    st.caption(f"Wallets: {stats['total_wallets']:,}")

# ---------------------------------------------------------------------------
# Main page content (welcome / overview)
# ---------------------------------------------------------------------------
st.title(":crystal_ball: OracleBot Dashboard")
st.markdown(
    "Read-only analytics dashboard for detecting **sharp money** on Polymarket. "
    "Navigate using the sidebar pages."
)

# Quick stats row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Markets", f"{stats['total_markets']:,}")
c2.metric("Resolved", f"{stats['resolved_markets']:,}")
c3.metric("Total Trades", f"{stats['total_bets']:,}")
c4.metric("Wallets Tracked", f"{stats['total_wallets']:,}")

st.divider()
st.info(
    "Use the **sidebar** to navigate between pages: "
    "Dashboard, Markets, Wallets, Method Performance, Combo Results, Reports, Settings."
)
