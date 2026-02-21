"""Dashboard — Top picks, DB stats, best combo, suspicious wallets."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st

from gui.db_queries import (
    get_db_stats,
    get_suspicious_wallets,
    get_top_combos,
    parse_latest_report,
)
from gui.components import render_pick_card, COLORS

st.set_page_config(page_title="OracleBot — Dashboard", layout="wide")
st.title(":bar_chart: Dashboard")

# ---------------------------------------------------------------------------
# DB stats
# ---------------------------------------------------------------------------
stats = get_db_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Markets", f"{stats['total_markets']:,}")
c2.metric("Resolved", f"{stats['resolved_markets']:,}")
c3.metric("Total Trades", f"{stats['total_bets']:,}")
c4.metric("Wallets Tracked", f"{stats['total_wallets']:,}")

st.divider()

# ---------------------------------------------------------------------------
# Top picks from latest report
# ---------------------------------------------------------------------------
top_picks, table_picks = parse_latest_report()

st.subheader("Top Picks")

if top_picks:
    for pick in top_picks[:3]:
        render_pick_card(
            rank=pick["rank"],
            title=pick["title"],
            side=pick["side"],
            yes_price=pick["yes_price"],
            edge=pick["edge"],
            confidence=pick["confidence"],
            madness=pick["madness"],
            n_bets=pick["n_bets"],
        )
else:
    st.info("No picks available yet — run the engine to generate a report.")

# Other exploitable markets
if table_picks:
    st.subheader("All Exploitable Markets")
    import pandas as pd
    tp_df = pd.DataFrame(table_picks)
    tp_df = tp_df.rename(columns={
        "rank": "#", "title": "Market", "side": "Action",
        "buy_at": "Buy At", "edge": "Edge",
        "confidence": "Conf", "madness": "Madness",
    })
    st.dataframe(tp_df, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Two-column: best combo + suspicious wallets
# ---------------------------------------------------------------------------
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Best Combo")
    combos_df = get_top_combos(limit=5)
    if not combos_df.empty:
        for _, row in combos_df.iterrows():
            methods_str = ", ".join(row["methods_used"])
            st.markdown(
                f"**{row['combo_id']}**  \n"
                f"Accuracy: `{row['accuracy']:.1%}` | "
                f"Edge: `{row['edge_vs_market']:+.3f}` | "
                f"FPR: `{row['false_positive_rate']:.1%}` | "
                f"Fitness: **{row['fitness_score']:.4f}**"
            )
    else:
        st.info("No combo results yet — run optimization first.")

with col_right:
    st.subheader("Suspicious Wallets")
    sus_df = get_suspicious_wallets(limit=10)
    if not sus_df.empty:
        display_df = sus_df.copy()
        display_df["address"] = display_df["address"].str[:14] + "..."
        display_df["win_rate"] = display_df["win_rate"].apply(lambda x: f"{x:.0%}")
        display_df["total_volume"] = display_df["total_volume"].apply(lambda x: f"${x:,.0f}")
        display_df = display_df.rename(columns={
            "address": "Wallet", "win_rate": "Win Rate",
            "total_bets": "Bets", "total_volume": "Volume",
        })
        st.dataframe(
            display_df[["Wallet", "Win Rate", "Bets", "Volume"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No suspicious wallets flagged yet.")
