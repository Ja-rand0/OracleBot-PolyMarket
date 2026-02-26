"""Method Performance — Per-method contribution analysis and co-occurrence."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from gui.db_queries import get_method_performance, get_method_cooccurrence
from gui.components import METHOD_INFO, CATEGORY_NAMES, category_color

st.set_page_config(page_title="OracleBot — Method Performance", layout="wide")
st.title(":microscope: Method Performance")

# ---------------------------------------------------------------------------
# Per-method table
# ---------------------------------------------------------------------------
perf_df = get_method_performance()

if perf_df.empty:
    st.info("No combo results in the database yet — run optimization to populate method performance data.")
    st.stop()

st.subheader("Method Overview")
display_df = perf_df.copy()
display_df = display_df.rename(columns={
    "method_id": "Method", "category": "Cat", "description": "Description",
    "frequency": "In Combos", "avg_fitness_present": "Avg Fitness (Present)",
    "avg_fitness_absent": "Avg Fitness (Absent)", "marginal": "Marginal Contribution",
})
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Marginal contribution chart
# ---------------------------------------------------------------------------
st.subheader("Marginal Contribution by Method")
st.caption("Positive = method improves combo fitness. Negative = method hurts.")

perf_sorted = perf_df.sort_values("marginal", ascending=True)
colors = [category_color(METHOD_INFO.get(m, ("?", ""))[0]) for m in perf_sorted["method_id"]]

fig = go.Figure(go.Bar(
    x=perf_sorted["marginal"],
    y=perf_sorted["method_id"],
    orientation="h",
    marker_color=colors,
    text=perf_sorted["marginal"].apply(lambda x: f"{x:+.4f}"),
    textposition="outside",
))
fig.update_layout(
    height=max(400, len(perf_sorted) * 22),
    xaxis_title="Marginal Contribution to Fitness",
    yaxis_title="Method",
    margin=dict(l=60, r=20, t=10, b=40),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Category-level fitness
# ---------------------------------------------------------------------------
st.subheader("Average Fitness by Category")

cat_df = perf_df.groupby("category").agg(
    avg_fitness=("avg_fitness_present", "mean"),
    methods=("method_id", "count"),
    avg_marginal=("marginal", "mean"),
).reset_index()
cat_df["cat_name"] = cat_df["category"].map(CATEGORY_NAMES)
cat_colors = [category_color(c) for c in cat_df["category"]]

fig = px.bar(
    cat_df, x="cat_name", y="avg_fitness",
    color="category",
    color_discrete_map={c: category_color(c) for c in cat_df["category"]},
    labels={"cat_name": "Category", "avg_fitness": "Avg Fitness When Present"},
    text="avg_marginal",
)
fig.update_traces(texttemplate="%{text:+.4f}", textposition="outside")
fig.update_layout(height=400, showlegend=False)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Co-occurrence heatmap
# ---------------------------------------------------------------------------
st.subheader("Method Co-occurrence Matrix")
st.caption("How often pairs of methods appear together in top combos.")

cooc_df = get_method_cooccurrence()
if not cooc_df.empty:
    fig = go.Figure(data=go.Heatmap(
        z=cooc_df.values,
        x=cooc_df.columns.tolist(),
        y=cooc_df.index.tolist(),
        colorscale="Blues",
        text=cooc_df.values,
        texttemplate="%{text}",
        textfont={"size": 8},
    ))
    fig.update_layout(
        height=700,
        width=700,
        xaxis=dict(tickangle=45, tickfont=dict(size=9)),
        yaxis=dict(tickfont=dict(size=9)),
        margin=dict(l=40, r=20, t=10, b=60),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Not enough combo data for co-occurrence analysis.")
