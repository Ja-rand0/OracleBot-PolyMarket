"""Markets — Filterable market table with drill-down and charts."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from gui.db_queries import (
    get_markets_paginated,
    get_market_detail,
    get_market_bet_summary,
    get_market_bet_volume_over_time,
    get_market_price_history,
    get_market_recent_bets,
    get_market_top_wallets,
)
from gui.components import COLORS

st.set_page_config(page_title="OracleBot — Markets", layout="wide")
st.title(":chart_with_upwards_trend: Markets")

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1, 1, 1])
with col_f1:
    search = st.text_input("Search markets", placeholder="Type to filter by title...")
with col_f2:
    status = st.selectbox("Status", ["all", "active", "resolved"])
with col_f3:
    min_bets = st.number_input("Min bets", min_value=0, value=0, step=5)
with col_f4:
    sort_by = st.selectbox("Sort by", ["volume", "bets", "end_date", "created", "title"])

# Pagination
PAGE_SIZE = 50
if "market_page" not in st.session_state:
    st.session_state.market_page = 0

offset = st.session_state.market_page * PAGE_SIZE
df, total = get_markets_paginated(
    status=status, search=search, min_bets=min_bets,
    sort_by=sort_by, limit=PAGE_SIZE, offset=offset,
)

total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
st.caption(f"Showing {offset+1}–{min(offset+PAGE_SIZE, total)} of {total:,} markets")

# Page navigation
nav_c1, nav_c2, nav_c3 = st.columns([1, 2, 1])
with nav_c1:
    if st.button("Previous", disabled=st.session_state.market_page <= 0):
        st.session_state.market_page -= 1
        st.rerun()
with nav_c3:
    if st.button("Next", disabled=st.session_state.market_page >= total_pages - 1):
        st.session_state.market_page += 1
        st.rerun()

# ---------------------------------------------------------------------------
# Market table
# ---------------------------------------------------------------------------
if not df.empty:
    display_df = df.copy()
    display_df["resolved"] = display_df["resolved"].apply(lambda x: "Resolved" if x else "Active")
    display_df["total_volume"] = display_df["total_volume"].apply(lambda x: f"${x:,.0f}")
    display_df = display_df.rename(columns={
        "title": "Title", "resolved": "Status", "outcome": "Outcome",
        "bet_count": "Bets", "total_volume": "Volume",
        "end_date": "End Date",
    })
    st.dataframe(
        display_df[["Title", "Status", "Outcome", "Bets", "Volume", "End Date"]],
        use_container_width=True,
        hide_index=True,
    )

    # ---------------------------------------------------------------------------
    # Market drill-down
    # ---------------------------------------------------------------------------
    st.divider()
    st.subheader("Market Detail")

    market_options = dict(zip(df["title"].str[:60], df["id"]))
    selected_title = st.selectbox("Select a market", [""] + list(market_options.keys()))

    if selected_title and selected_title in market_options:
        market_id = market_options[selected_title]
        detail = get_market_detail(market_id)

        if detail:
            st.markdown(f"### {detail['title']}")
            if detail.get("description"):
                st.caption(detail["description"][:500])

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Status", "Resolved" if detail["resolved"] else "Active")
            mc2.metric("Outcome", detail.get("outcome") or "—")
            mc3.metric("End Date", str(detail.get("end_date", "—"))[:10])

            # Bet summary
            summary = get_market_bet_summary(market_id)
            if not summary.empty:
                sc1, sc2 = st.columns(2)
                for _, row in summary.iterrows():
                    col = sc1 if row["side"] == "YES" else sc2
                    col.metric(
                        f"{row['side']} Bets",
                        f"{int(row['count']):,}",
                        f"${row['volume']:,.0f} volume",
                    )

            # Charts
            chart_c1, chart_c2 = st.columns(2)

            with chart_c1:
                vol_df = get_market_bet_volume_over_time(market_id)
                if not vol_df.empty:
                    fig = px.bar(
                        vol_df, x="date", y="volume", color="side",
                        color_discrete_map={"YES": COLORS["yes"], "NO": COLORS["no"]},
                        title="Volume Over Time",
                        labels={"date": "Date", "volume": "Volume ($)", "side": "Side"},
                    )
                    fig.update_layout(barmode="stack", height=350)
                    st.plotly_chart(fig, use_container_width=True)

            with chart_c2:
                price_df = get_market_price_history(market_id)
                if not price_df.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=price_df["hour"], y=price_df["vwap"],
                        mode="lines+markers", name="YES Prob (VWAP)",
                        line=dict(color=COLORS["yes"], width=2),
                        marker=dict(size=3),
                    ))
                    fig.update_layout(
                        title="Price History (Hourly VWAP)",
                        yaxis=dict(title="YES Probability", range=[0, 1]),
                        xaxis=dict(title="Time"),
                        height=350,
                    )
                    st.plotly_chart(fig, use_container_width=True)

            # Recent bets
            st.markdown("#### Recent Bets")
            recent = get_market_recent_bets(market_id)
            if not recent.empty:
                recent_display = recent.copy()
                recent_display["wallet"] = recent_display["wallet"].str[:14] + "..."
                recent_display["amount"] = recent_display["amount"].apply(lambda x: f"${x:,.2f}")
                recent_display["odds"] = recent_display["odds"].apply(lambda x: f"{x:.2f}")
                st.dataframe(recent_display, use_container_width=True, hide_index=True)

            # Top wallets
            st.markdown("#### Top Wallets in This Market")
            top_w = get_market_top_wallets(market_id)
            if not top_w.empty:
                tw_display = top_w.copy()
                tw_display["wallet"] = tw_display["wallet"].str[:14] + "..."
                tw_display["volume"] = tw_display["volume"].apply(lambda x: f"${x:,.0f}")
                tw_display["dominant"] = tw_display.apply(
                    lambda r: "YES" if r["yes_count"] > r["no_count"] else "NO", axis=1
                )
                st.dataframe(
                    tw_display[["wallet", "bets", "volume", "avg_odds", "dominant"]],
                    use_container_width=True, hide_index=True,
                )
else:
    st.info("No markets match the current filters.")
