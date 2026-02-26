"""Wallets — Search, profile cards, trade history, aggregate stats."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import plotly.express as px

from gui.db_queries import (
    get_wallets_paginated,
    get_wallet_detail,
    get_wallet_bets,
    get_wallet_market_distribution,
    get_wallet_bet_sizes,
    get_wallet_flag_counts,
    get_rationality_distribution,
)
from gui.components import COLORS, wallet_flags_html

st.set_page_config(page_title="OracleBot — Wallets", layout="wide")
st.title(":bust_in_silhouette: Wallets")

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
col_f1, col_f2, col_f3 = st.columns([3, 1, 1])
with col_f1:
    search = st.text_input("Search by address", placeholder="0x...")
with col_f2:
    filter_type = st.selectbox("Filter", ["all", "suspicious", "sandpit", "high_winrate", "high_volume"])
with col_f3:
    sort_by = st.selectbox("Sort by", ["volume", "bets", "win_rate", "rationality"])

# Pagination
PAGE_SIZE = 50
if "wallet_page" not in st.session_state:
    st.session_state.wallet_page = 0

offset = st.session_state.wallet_page * PAGE_SIZE
df, total = get_wallets_paginated(
    search=search, filter_type=filter_type, sort_by=sort_by,
    limit=PAGE_SIZE, offset=offset,
)

total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
st.caption(f"Showing {offset + 1}–{min(offset + PAGE_SIZE, total)} of {total:,} wallets")

nav_c1, nav_c2, nav_c3 = st.columns([1, 2, 1])
with nav_c1:
    if st.button("Previous", disabled=st.session_state.wallet_page <= 0):
        st.session_state.wallet_page -= 1
        st.rerun()
with nav_c3:
    if st.button("Next", disabled=st.session_state.wallet_page >= total_pages - 1):
        st.session_state.wallet_page += 1
        st.rerun()

# ---------------------------------------------------------------------------
# Wallet table
# ---------------------------------------------------------------------------
if not df.empty:
    display_df = df.copy()
    display_df["address_short"] = display_df["address"].str[:14] + "..."
    display_df["win_rate"] = display_df["win_rate"].apply(lambda x: f"{x:.0%}")
    display_df["total_volume"] = display_df["total_volume"].apply(lambda x: f"${x:,.0f}")
    display_df["rationality_score"] = display_df["rationality_score"].apply(lambda x: f"{x:.2f}")
    display_df["flags"] = display_df.apply(
        lambda r: ("Suspicious " if r["flagged_suspicious"] else "") +
                  ("Sandpit" if r["flagged_sandpit"] else "") or "Clean",
        axis=1,
    )
    st.dataframe(
        display_df[["address_short", "total_bets", "total_volume", "win_rate",
                    "rationality_score", "flags"]].rename(columns={
                        "address_short": "Address", "total_bets": "Bets",
                        "total_volume": "Volume", "win_rate": "Win Rate",
                        "rationality_score": "Rationality", "flags": "Flags",
                    }),
        use_container_width=True, hide_index=True,
    )

    # ---------------------------------------------------------------------------
    # Wallet drill-down
    # ---------------------------------------------------------------------------
    st.divider()
    st.subheader("Wallet Profile")

    wallet_options = list(df["address"])
    wallet_labels = [f"{a[:14]}... ({df.loc[df['address'] == a, 'total_bets'].values[0]} bets)" for a in wallet_options]
    selected_idx = st.selectbox("Select wallet", range(len(wallet_labels)),
                                format_func=lambda i: wallet_labels[i] if i < len(wallet_labels) else "")

    if selected_idx is not None and selected_idx < len(wallet_options):
        address = wallet_options[selected_idx]
        detail = get_wallet_detail(address)

        if detail:
            st.markdown(f"**Address:** `{detail['address']}`")
            st.markdown(wallet_flags_html(detail["flagged_suspicious"],
                        detail["flagged_sandpit"]), unsafe_allow_html=True)

            wc1, wc2, wc3, wc4 = st.columns(4)
            wc1.metric("Win Rate", f"{detail['win_rate']:.0%}")
            wc2.metric("Rationality", f"{detail['rationality_score']:.2f}")
            wc3.metric("Total Volume", f"${detail['total_volume']:,.0f}")
            wc4.metric("Total Bets", f"{detail['total_bets']:,}")

            # Charts
            chart_c1, chart_c2 = st.columns(2)

            with chart_c1:
                mkt_dist = get_wallet_market_distribution(address)
                if not mkt_dist.empty:
                    mkt_dist["title"] = mkt_dist["title"].str[:40]
                    fig = px.bar(
                        mkt_dist, x="volume", y="title", orientation="h",
                        title="Top Markets by Volume",
                        labels={"volume": "Volume ($)", "title": "Market"},
                        color_discrete_sequence=[COLORS["rational"]],
                    )
                    fig.update_layout(height=350, yaxis=dict(autorange="reversed"))
                    st.plotly_chart(fig, use_container_width=True)

            with chart_c2:
                bet_sizes = get_wallet_bet_sizes(address)
                if bet_sizes:
                    fig = px.histogram(
                        x=bet_sizes, nbins=30,
                        title="Bet Size Distribution",
                        labels={"x": "Bet Amount ($)", "y": "Count"},
                        color_discrete_sequence=[COLORS["emotional"]],
                    )
                    fig.update_layout(height=350)
                    st.plotly_chart(fig, use_container_width=True)

            # Trade history
            st.markdown("#### Trade History")
            if "wallet_bet_page" not in st.session_state:
                st.session_state.wallet_bet_page = 0
            bet_offset = st.session_state.wallet_bet_page * 50
            bets_df, bet_total = get_wallet_bets(address, limit=50, offset=bet_offset)
            if not bets_df.empty:
                bets_display = bets_df.copy()
                if "title" in bets_display.columns:
                    bets_display["title"] = bets_display["title"].str[:40]
                bets_display["amount"] = bets_display["amount"].apply(lambda x: f"${x:,.2f}")
                bets_display["odds"] = bets_display["odds"].apply(lambda x: f"{x:.2f}")
                st.dataframe(bets_display, use_container_width=True, hide_index=True)
                st.caption(f"Showing {bet_offset + 1}–{min(bet_offset + 50, bet_total)} of {bet_total:,}")

st.divider()

# ---------------------------------------------------------------------------
# Aggregate stats
# ---------------------------------------------------------------------------
st.subheader("Aggregate Wallet Stats")

agg_c1, agg_c2 = st.columns(2)

with agg_c1:
    rat_df = get_rationality_distribution()
    if not rat_df.empty:
        fig = px.bar(
            rat_df, x="bucket", y="count",
            title="Rationality Score Distribution",
            labels={"bucket": "Score Range", "count": "Wallets"},
            color_discrete_sequence=[COLORS["rational"]],
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

with agg_c2:
    flag_counts = get_wallet_flag_counts()
    if flag_counts:
        import pandas as pd
        flag_df = pd.DataFrame([
            {"Flag": "Suspicious", "Count": flag_counts.get("suspicious", 0)},
            {"Flag": "Sandpit", "Count": flag_counts.get("sandpit", 0)},
            {"Flag": "Clean", "Count": flag_counts.get("clean", 0)},
        ])
        fig = px.pie(
            flag_df, values="Count", names="Flag",
            title="Wallet Flag Distribution",
            color="Flag",
            color_discrete_map={
                "Suspicious": COLORS["suspicious"],
                "Sandpit": COLORS["sandpit"],
                "Clean": COLORS["neutral"],
            },
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
