"""Settings — Read-only display of all configuration constants."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import plotly.express as px
import pandas as pd

import config
from gui.db_queries import get_db_file_size

st.set_page_config(page_title="OracleBot — Settings", layout="wide")
st.title(":gear: Settings")
st.caption("Read-only view of current configuration. Edit `config.py` to change values.")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
st.subheader("Database")
dc1, dc2, dc3 = st.columns(3)
dc1.metric("Path", config.DB_PATH)
dc2.metric("File Size", f"{get_db_file_size():.1f} MB")
dc3.metric("Mode", "WAL (Write-Ahead Log)")

st.divider()

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
st.subheader("API Endpoints")
st.markdown(f"""
| Endpoint | URL |
|----------|-----|
| Polymarket CLOB | `{config.POLYMARKET_BASE_URL}` |
| Gamma API | `{config.GAMMA_BASE_URL}` |
| Polygonscan | `{config.POLYGONSCAN_BASE_URL}` |
""")

st.divider()

# ---------------------------------------------------------------------------
# Scraper Settings
# ---------------------------------------------------------------------------
st.subheader("Scraper Settings")
sc1, sc2, sc3 = st.columns(3)
sc1.metric("Scrape Interval", f"{config.SCRAPE_INTERVAL_MINUTES} min")
sc2.metric("Request Timeout", f"{config.API_REQUEST_TIMEOUT}s")
sc3.metric("Max Retries", str(config.API_MAX_RETRIES))

sc4, sc5, sc6 = st.columns(3)
sc4.metric("Retry Backoff", f"{config.API_RETRY_BACKOFF}x")
sc5.metric("Markets Page Size", str(config.MARKETS_PAGE_SIZE))
sc6.metric("Trades Page Size", str(config.TRADES_PAGE_SIZE))

st.divider()

# ---------------------------------------------------------------------------
# Fitness Weights
# ---------------------------------------------------------------------------
st.subheader("Fitness Function Weights")
st.markdown(
    f"`fitness = accuracy * {config.FITNESS_W_ACCURACY} + edge * {config.FITNESS_W_EDGE} "
    f"- FPR * {config.FITNESS_W_FALSE_POS} - (complexity/{config.TOTAL_METHODS}) * {config.FITNESS_W_COMPLEXITY}`"
)

weights_df = pd.DataFrame([
    {"Component": "Accuracy", "Weight": config.FITNESS_W_ACCURACY},
    {"Component": "Edge vs Market", "Weight": config.FITNESS_W_EDGE},
    {"Component": "False Positive Rate", "Weight": config.FITNESS_W_FALSE_POS},
    {"Component": "Complexity Penalty", "Weight": config.FITNESS_W_COMPLEXITY},
])
fig = px.pie(
    weights_df, values="Weight", names="Component",
    color_discrete_sequence=["#22c55e", "#3b82f6", "#ef4444", "#6b7280"],
)
fig.update_layout(height=300)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Combinator & Backtest
# ---------------------------------------------------------------------------
st.subheader("Combinator & Backtest")
cb1, cb2, cb3 = st.columns(3)
cb1.metric("Tier 1 Top Per Category", str(config.TIER1_TOP_PER_CATEGORY))
cb2.metric("Tier 2 Top Overall", str(config.TIER2_TOP_OVERALL))
cb3.metric("Backtest Cutoff", f"{config.BACKTEST_CUTOFF_FRACTION:.0%}")

st.divider()

# ---------------------------------------------------------------------------
# Method Thresholds
# ---------------------------------------------------------------------------
st.subheader("Method Thresholds")

# Collect all threshold constants from config
threshold_groups = {
    "S — Suspicious": [
        ("S1_MIN_RESOLVED_BETS", config.S1_MIN_RESOLVED_BETS),
        ("S1_STDDEV_THRESHOLD", config.S1_STDDEV_THRESHOLD),
        ("S3_TIME_WINDOW_MINUTES", config.S3_TIME_WINDOW_MINUTES),
        ("S3_MIN_CO_MARKETS", config.S3_MIN_CO_MARKETS),
        ("S3_MIN_CLUSTER_SIZE", config.S3_MIN_CLUSTER_SIZE),
        ("S4_SANDPIT_MIN_BETS", config.S4_SANDPIT_MIN_BETS),
        ("S4_SANDPIT_MAX_WIN_RATE", config.S4_SANDPIT_MAX_WIN_RATE),
        ("S4_SANDPIT_MIN_VOLUME", config.S4_SANDPIT_MIN_VOLUME),
        ("S4_NEW_WALLET_MAX_BETS", config.S4_NEW_WALLET_MAX_BETS),
        ("S4_NEW_WALLET_LARGE_BET", config.S4_NEW_WALLET_LARGE_BET),
    ],
    "D — Discrete": [
        ("D7_MIN_BETS", config.D7_MIN_BETS),
    ],
    "E — Emotional": [
        ("E10_CONSISTENCY_THRESHOLD", config.E10_CONSISTENCY_THRESHOLD),
        ("E10_MIN_MARKETS", config.E10_MIN_MARKETS),
        ("E12_WINDOW_HOURS", config.E12_WINDOW_HOURS),
        ("E13_VOLUME_SPIKE_MULTIPLIER", config.E13_VOLUME_SPIKE_MULTIPLIER),
        ("E14_LOW_CORRELATION_THRESHOLD", config.E14_LOW_CORRELATION_THRESHOLD),
        ("E15_ROUND_DIVISOR", config.E15_ROUND_DIVISOR),
        ("E16_KL_THRESHOLD", config.E16_KL_THRESHOLD),
    ],
    "T — Statistical": [
        ("T17_PRIOR_WEIGHT", config.T17_PRIOR_WEIGHT),
        ("T17_AMOUNT_NORMALIZER", config.T17_AMOUNT_NORMALIZER),
        ("T17_UPDATE_STEP", config.T17_UPDATE_STEP),
        ("T17_RATIONALITY_CUTOFF", config.T17_RATIONALITY_CUTOFF),
        ("T18_CHI_SQUARED_PVALUE", config.T18_CHI_SQUARED_PVALUE),
        ("T19_ZSCORE_THRESHOLD", config.T19_ZSCORE_THRESHOLD),
    ],
    "P — Psychological": [
        ("P20_DEVIATION_THRESHOLD", config.P20_DEVIATION_THRESHOLD),
        ("P21_LOW_PROB", config.P21_LOW_PROB),
        ("P21_HIGH_PROB", config.P21_HIGH_PROB),
        ("P22_TIME_WINDOW_MINUTES", config.P22_TIME_WINDOW_MINUTES),
        ("P22_MIN_HERD_SIZE", config.P22_MIN_HERD_SIZE),
        ("P23_ANCHOR_MIN_AMOUNT", config.P23_ANCHOR_MIN_AMOUNT),
        ("P24_LOW_RATIO", config.P24_LOW_RATIO),
        ("P24_HIGH_RATIO", config.P24_HIGH_RATIO),
    ],
    "M — Markov": [
        ("M26_NUM_WINDOWS", config.M26_NUM_WINDOWS),
        ("M26_LOW_THRESHOLD", config.M26_LOW_THRESHOLD),
        ("M26_HIGH_THRESHOLD", config.M26_HIGH_THRESHOLD),
        ("M26_TRENDING_THRESHOLD", config.M26_TRENDING_THRESHOLD),
        ("M27_NUM_WINDOWS", config.M27_NUM_WINDOWS),
        ("M27_FLOW_THRESHOLD", config.M27_FLOW_THRESHOLD),
        ("M27_MOMENTUM_THRESHOLD", config.M27_MOMENTUM_THRESHOLD),
        ("M28_SMART_THRESHOLD", config.M28_SMART_THRESHOLD),
        ("M28_RETAIL_THRESHOLD", config.M28_RETAIL_THRESHOLD),
        ("M28_NUM_WINDOWS", config.M28_NUM_WINDOWS),
        ("M28_MIN_SMART_WALLETS", config.M28_MIN_SMART_WALLETS),
        ("M28_MIN_RETAIL_WALLETS", config.M28_MIN_RETAIL_WALLETS),
    ],
}

for group_name, constants in threshold_groups.items():
    with st.expander(group_name, expanded=False):
        thresh_df = pd.DataFrame(constants, columns=["Constant", "Value"])
        st.dataframe(thresh_df, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Report Settings
# ---------------------------------------------------------------------------
st.subheader("Report Settings")
rc1, rc2, rc3 = st.columns(3)
rc1.metric("Recent Trades for Price", str(config.REPORT_PRICE_RECENT_TRADES))
rc2.metric("Min Trades for Price", str(config.REPORT_PRICE_MIN_TRADES))
rc3.metric("Total Methods", str(config.TOTAL_METHODS))
