"""Reports — Historical daily report viewer."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st

from gui.db_queries import list_reports, read_report

st.set_page_config(page_title="OracleBot — Reports", layout="wide")
st.title(":page_facing_up: Reports")

reports = list_reports()

if not reports:
    st.info("No reports found in the `reports/` directory. Run the engine to generate daily reports.")
    st.stop()

# ---------------------------------------------------------------------------
# Report selector
# ---------------------------------------------------------------------------
report_names = [name for name, _ in reports]
selected = st.selectbox("Select report", report_names)

if selected:
    filepath = dict(reports)[selected]
    content = read_report(filepath)

    if content:
        st.markdown("---")
        st.markdown(content)
    else:
        st.warning(f"Could not read report: {filepath}")

st.divider()
st.caption(f"{len(reports)} report(s) available")
