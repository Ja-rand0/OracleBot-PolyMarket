"""Combo Results — Top combos, fitness breakdown, complexity analysis."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

import config
from gui.db_queries import get_top_combos
from gui.components import method_badges_html, COLORS

st.set_page_config(page_title="OracleBot — Combo Results", layout="wide")
st.title(":trophy: Combo Results")

combos_df = get_top_combos(limit=50)

if combos_df.empty:
    st.info("No combo results in the database — run optimization first.")
    st.stop()

# ---------------------------------------------------------------------------
# Combo table
# ---------------------------------------------------------------------------
st.subheader(f"Top {len(combos_df)} Combos")

display_df = combos_df.copy()
display_df["rank"] = range(1, len(display_df) + 1)
display_df["methods_str"] = display_df["methods_used"].apply(lambda ms: ", ".join(ms))
display_df["accuracy"] = display_df["accuracy"].apply(lambda x: f"{x:.1%}")
display_df["edge_vs_market"] = display_df["edge_vs_market"].apply(lambda x: f"{x:+.3f}")
display_df["false_positive_rate"] = display_df["false_positive_rate"].apply(lambda x: f"{x:.1%}")
display_df["fitness_score"] = display_df["fitness_score"].apply(lambda x: f"{x:.4f}")

st.dataframe(
    display_df[["rank", "combo_id", "methods_str", "accuracy", "edge_vs_market",
                "false_positive_rate", "complexity", "fitness_score"]].rename(columns={
                    "rank": "#", "combo_id": "Combo", "methods_str": "Methods",
                    "accuracy": "Accuracy", "edge_vs_market": "Edge",
                    "false_positive_rate": "FPR", "complexity": "Size",
                    "fitness_score": "Fitness",
                }),
    use_container_width=True, hide_index=True,
)

st.divider()

# ---------------------------------------------------------------------------
# Fitness breakdown chart (top 10)
# ---------------------------------------------------------------------------
st.subheader("Fitness Component Breakdown (Top 10)")
st.caption(
    f"Accuracy x{config.FITNESS_W_ACCURACY} + Edge x{config.FITNESS_W_EDGE} "
    f"- FPR x{config.FITNESS_W_FALSE_POS} - Complexity/{config.TOTAL_METHODS} x{config.FITNESS_W_COMPLEXITY}"
)

top10 = combos_df.head(10).copy()
top10["acc_component"] = top10["accuracy"].apply(lambda x: float(
    x.strip('%')) / 100 if isinstance(x, str) else x) if top10["accuracy"].dtype == object else top10["accuracy"]

# Recompute from raw values
raw = get_top_combos(limit=10)
raw["acc_c"] = raw["accuracy"] * config.FITNESS_W_ACCURACY
raw["edge_c"] = raw["edge_vs_market"] * config.FITNESS_W_EDGE
raw["fpr_c"] = -raw["false_positive_rate"] * config.FITNESS_W_FALSE_POS
raw["complexity_c"] = -(raw["complexity"] / config.TOTAL_METHODS) * config.FITNESS_W_COMPLEXITY

fig = go.Figure()
fig.add_trace(go.Bar(
    name="Accuracy", y=raw["combo_id"], x=raw["acc_c"],
    orientation="h", marker_color=COLORS["yes"],
))
fig.add_trace(go.Bar(
    name="Edge", y=raw["combo_id"], x=raw["edge_c"],
    orientation="h", marker_color=COLORS["rational"],
))
fig.add_trace(go.Bar(
    name="FPR (penalty)", y=raw["combo_id"], x=raw["fpr_c"],
    orientation="h", marker_color=COLORS["no"],
))
fig.add_trace(go.Bar(
    name="Complexity (penalty)", y=raw["combo_id"], x=raw["complexity_c"],
    orientation="h", marker_color=COLORS["neutral"],
))
fig.update_layout(
    barmode="relative",
    height=max(350, len(raw) * 40),
    xaxis_title="Fitness Contribution",
    yaxis=dict(autorange="reversed"),
    margin=dict(l=120, r=20, t=10, b=40),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Complexity vs Fitness scatter
# ---------------------------------------------------------------------------
st.subheader("Complexity vs Fitness")
scatter_df = get_top_combos(limit=50)

fig = px.scatter(
    scatter_df, x="complexity", y="fitness_score",
    hover_data=["combo_id"],
    labels={"complexity": "Combo Size (# methods)", "fitness_score": "Fitness Score"},
    color_discrete_sequence=[COLORS["suspicious"]],
)
fig.update_traces(marker=dict(size=10))
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Combo detail
# ---------------------------------------------------------------------------
st.subheader("Combo Detail")
combo_options = list(combos_df["combo_id"])
selected_combo = st.selectbox("Select a combo", [""] + combo_options)

if selected_combo:
    row = combos_df[combos_df["combo_id"] == selected_combo].iloc[0]
    st.markdown(f"**Combo:** `{row['combo_id']}`")
    st.markdown(method_badges_html(row["methods_used"]), unsafe_allow_html=True)

    dc1, dc2, dc3, dc4 = st.columns(4)
    acc_val = float(row["accuracy"].strip('%')) / 100 if isinstance(row["accuracy"], str) else row["accuracy"]
    fpr_val = float(row["false_positive_rate"].strip('%')) / \
        100 if isinstance(row["false_positive_rate"], str) else row["false_positive_rate"]
    edge_val = float(row["edge_vs_market"]) if isinstance(row["edge_vs_market"], str) else row["edge_vs_market"]
    fit_val = float(row["fitness_score"]) if isinstance(row["fitness_score"], str) else row["fitness_score"]

    dc1.metric("Accuracy", f"{acc_val:.1%}")
    dc2.metric("Edge vs Market", f"{edge_val:+.3f}")
    dc3.metric("False Positive Rate", f"{fpr_val:.1%}")
    dc4.metric("Fitness", f"{fit_val:.4f}")
