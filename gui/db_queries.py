"""Cached SQL queries for the OracleBot Streamlit dashboard.

All database access for the GUI goes through this module.
Every public function uses @st.cache_data with appropriate TTLs.
Connections are opened/closed per query call — thread-safe for Streamlit.
PRAGMA query_only=ON prevents accidental writes.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st

import config

# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------
_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA query_only=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Database stats
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_db_stats() -> dict:
    conn = _get_conn()
    try:
        row = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM markets) AS total_markets,
                (SELECT COUNT(*) FROM markets WHERE resolved=1) AS resolved_markets,
                (SELECT COUNT(*) FROM bets) AS total_bets,
                (SELECT COUNT(*) FROM wallets) AS total_wallets
        """).fetchone()
        return dict(row)
    finally:
        conn.close()


@st.cache_data(ttl=60)
def get_db_file_size() -> float:
    try:
        return os.path.getsize(config.DB_PATH) / (1024 * 1024)
    except OSError:
        return 0.0


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------
@st.cache_data(ttl=120)
def get_markets_paginated(
    status: str = "all",
    search: str = "",
    min_bets: int = 0,
    sort_by: str = "volume",
    limit: int = 50,
    offset: int = 0,
) -> tuple[pd.DataFrame, int]:
    conn = _get_conn()
    try:
        where_clauses = []
        params: list = []

        if status == "active":
            where_clauses.append("m.resolved = 0")
        elif status == "resolved":
            where_clauses.append("m.resolved = 1")

        if search:
            where_clauses.append("m.title LIKE ?")
            params.append(f"%{search}%")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        having_sql = ""
        if min_bets > 0:
            having_sql = f"HAVING COUNT(b.id) >= {int(min_bets)}"

        sort_map = {
            "volume": "total_volume DESC",
            "bets": "bet_count DESC",
            "end_date": "m.end_date DESC",
            "created": "m.created_at DESC",
            "title": "m.title ASC",
        }
        order_sql = sort_map.get(sort_by, "total_volume DESC")

        # Count query
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT m.id
                FROM markets m
                LEFT JOIN bets b ON m.id = b.market_id
                {where_sql}
                GROUP BY m.id
                {having_sql}
            )
        """
        total = conn.execute(count_sql, params).fetchone()[0]

        # Data query
        data_sql = f"""
            SELECT m.id, m.title, m.end_date, m.resolved, m.outcome, m.created_at,
                   COUNT(b.id) AS bet_count,
                   COALESCE(SUM(b.amount), 0) AS total_volume
            FROM markets m
            LEFT JOIN bets b ON m.id = b.market_id
            {where_sql}
            GROUP BY m.id
            {having_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(data_sql, params + [limit, offset]).fetchall()

        df = pd.DataFrame(
            [dict(r) for r in rows],
            columns=["id", "title", "end_date", "resolved", "outcome",
                      "created_at", "bet_count", "total_volume"],
        )
        return df, total
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_market_detail(market_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM markets WHERE id = ?", (market_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_market_bet_summary(market_id: str) -> pd.DataFrame:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT side, COUNT(*) as count, SUM(amount) as volume,
                   AVG(odds) as avg_odds
            FROM bets WHERE market_id = ?
            GROUP BY side
        """, (market_id,)).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_market_bet_volume_over_time(market_id: str) -> pd.DataFrame:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT DATE(timestamp) as date, side,
                   COUNT(*) as count, SUM(amount) as volume
            FROM bets WHERE market_id = ?
            GROUP BY DATE(timestamp), side
            ORDER BY date
        """, (market_id,)).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_market_price_history(market_id: str) -> pd.DataFrame:
    """Hourly VWAP for YES probability."""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT strftime('%Y-%m-%d %H:00', timestamp) as hour,
                   SUM(CASE WHEN side='YES' THEN odds * amount
                            ELSE (1.0 - odds) * amount END) / SUM(amount) as vwap,
                   COUNT(*) as trades
            FROM bets WHERE market_id = ?
            GROUP BY hour
            ORDER BY hour
        """, (market_id,)).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_market_recent_bets(market_id: str, limit: int = 50) -> pd.DataFrame:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT wallet, side, amount, odds, timestamp
            FROM bets WHERE market_id = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (market_id, limit)).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_market_top_wallets(market_id: str, limit: int = 20) -> pd.DataFrame:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT wallet, COUNT(*) as bets, SUM(amount) as volume,
                   AVG(odds) as avg_odds,
                   SUM(CASE WHEN side='YES' THEN 1 ELSE 0 END) as yes_count,
                   SUM(CASE WHEN side='NO' THEN 1 ELSE 0 END) as no_count
            FROM bets WHERE market_id = ?
            GROUP BY wallet ORDER BY volume DESC LIMIT ?
        """, (market_id, limit)).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Wallets
# ---------------------------------------------------------------------------
@st.cache_data(ttl=120)
def get_wallets_paginated(
    search: str = "",
    filter_type: str = "all",
    sort_by: str = "volume",
    limit: int = 50,
    offset: int = 0,
) -> tuple[pd.DataFrame, int]:
    conn = _get_conn()
    try:
        where_clauses = []
        params: list = []

        if search:
            where_clauses.append("address LIKE ?")
            params.append(f"{search}%")

        if filter_type == "suspicious":
            where_clauses.append("flagged_suspicious = 1")
        elif filter_type == "sandpit":
            where_clauses.append("flagged_sandpit = 1")
        elif filter_type == "high_winrate":
            where_clauses.append("win_rate >= 0.7 AND total_bets >= 10")
        elif filter_type == "high_volume":
            where_clauses.append("total_volume >= 10000")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sort_map = {
            "volume": "total_volume DESC",
            "bets": "total_bets DESC",
            "win_rate": "win_rate DESC",
            "rationality": "rationality_score DESC",
        }
        order_sql = sort_map.get(sort_by, "total_volume DESC")

        total = conn.execute(f"SELECT COUNT(*) FROM wallets {where_sql}", params).fetchone()[0]

        rows = conn.execute(f"""
            SELECT address, total_bets, total_volume, win_rate,
                   rationality_score, flagged_suspicious, flagged_sandpit
            FROM wallets {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()

        df = pd.DataFrame([dict(r) for r in rows])
        return df, total
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_wallet_detail(address: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM wallets WHERE address = ?", (address,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_wallet_bets(address: str, limit: int = 50, offset: int = 0) -> tuple[pd.DataFrame, int]:
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM bets WHERE wallet = ?", (address,)).fetchone()[0]
        rows = conn.execute("""
            SELECT b.market_id, b.side, b.amount, b.odds, b.timestamp, m.title
            FROM bets b
            JOIN markets m ON b.market_id = m.id
            WHERE b.wallet = ?
            ORDER BY b.timestamp DESC
            LIMIT ? OFFSET ?
        """, (address, limit, offset)).fetchall()
        df = pd.DataFrame([dict(r) for r in rows])
        return df, total
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_wallet_market_distribution(address: str, limit: int = 10) -> pd.DataFrame:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT m.title, SUM(b.amount) as volume, COUNT(*) as bets
            FROM bets b JOIN markets m ON b.market_id = m.id
            WHERE b.wallet = ?
            GROUP BY b.market_id
            ORDER BY volume DESC LIMIT ?
        """, (address, limit)).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


@st.cache_data(ttl=120)
def get_wallet_bet_sizes(address: str) -> list[float]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT amount FROM bets WHERE wallet = ?", (address,)
        ).fetchall()
        return [r["amount"] for r in rows]
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_suspicious_wallets(limit: int = 20) -> pd.DataFrame:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT address, win_rate, total_bets, total_volume, rationality_score
            FROM wallets
            WHERE flagged_suspicious = 1 AND total_bets >= 10
            ORDER BY win_rate DESC LIMIT ?
        """, (limit,)).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_wallet_flag_counts() -> dict:
    conn = _get_conn()
    try:
        row = conn.execute("""
            SELECT
                SUM(CASE WHEN flagged_suspicious=1 THEN 1 ELSE 0 END) as suspicious,
                SUM(CASE WHEN flagged_sandpit=1 THEN 1 ELSE 0 END) as sandpit,
                SUM(CASE WHEN flagged_suspicious=0 AND flagged_sandpit=0 THEN 1 ELSE 0 END) as clean
            FROM wallets
        """).fetchone()
        return dict(row)
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_rationality_distribution() -> pd.DataFrame:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT
                CASE
                    WHEN rationality_score < 0.2 THEN '0.0-0.2'
                    WHEN rationality_score < 0.4 THEN '0.2-0.4'
                    WHEN rationality_score < 0.6 THEN '0.4-0.6'
                    WHEN rationality_score < 0.8 THEN '0.6-0.8'
                    ELSE '0.8-1.0'
                END AS bucket,
                COUNT(*) as count
            FROM wallets
            GROUP BY bucket
            ORDER BY bucket
        """).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Combos / Method Results
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_top_combos(limit: int = 50) -> pd.DataFrame:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT combo_id, methods_used, accuracy, edge_vs_market,
                   false_positive_rate, complexity, fitness_score, tested_at
            FROM method_results
            ORDER BY fitness_score DESC LIMIT ?
        """, (limit,)).fetchall()
        data = []
        for r in rows:
            d = dict(r)
            d["methods_used"] = json.loads(d["methods_used"])
            data.append(d)
        return pd.DataFrame(data)
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_method_performance() -> pd.DataFrame:
    """Derive per-method stats from combo-level results.

    For each of the 28 methods, computes:
    - frequency: how many combos include this method
    - avg_fitness_present: mean fitness when this method is in the combo
    - avg_fitness_absent: mean fitness when it is NOT in the combo
    - marginal: avg_fitness_present - avg_fitness_absent
    """
    combos_df = get_top_combos(limit=50)
    if combos_df.empty:
        return pd.DataFrame()

    from gui.components import METHOD_INFO

    records = []
    for method_id, (cat, desc) in METHOD_INFO.items():
        present_mask = combos_df["methods_used"].apply(lambda ms: method_id in ms)
        present = combos_df[present_mask]
        absent = combos_df[~present_mask]

        freq = len(present)
        avg_present = present["fitness_score"].mean() if not present.empty else 0
        avg_absent = absent["fitness_score"].mean() if not absent.empty else 0

        records.append({
            "method_id": method_id,
            "category": cat,
            "description": desc,
            "frequency": freq,
            "avg_fitness_present": round(avg_present, 4),
            "avg_fitness_absent": round(avg_absent, 4),
            "marginal": round(avg_present - avg_absent, 4),
        })

    return pd.DataFrame(records)


@st.cache_data(ttl=300)
def get_method_cooccurrence() -> pd.DataFrame:
    """28x28 co-occurrence matrix: how often pairs appear together in combos."""
    combos_df = get_top_combos(limit=50)
    if combos_df.empty:
        return pd.DataFrame()

    from gui.components import METHOD_INFO
    method_ids = list(METHOD_INFO.keys())
    n = len(method_ids)
    idx_map = {m: i for i, m in enumerate(method_ids)}

    matrix = [[0] * n for _ in range(n)]
    for methods in combos_df["methods_used"]:
        ids_in_combo = [m for m in methods if m in idx_map]
        for i, a in enumerate(ids_in_combo):
            for b in ids_in_combo[i:]:
                matrix[idx_map[a]][idx_map[b]] += 1
                if a != b:
                    matrix[idx_map[b]][idx_map[a]] += 1

    return pd.DataFrame(matrix, index=method_ids, columns=method_ids)


# ---------------------------------------------------------------------------
# Report parsing
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def list_reports(reports_dir: str = "reports") -> list[tuple[str, str]]:
    pattern = os.path.join(reports_dir, "report_*.md")
    files = sorted(glob.glob(pattern), reverse=True)
    return [(os.path.basename(f), f) for f in files]


@st.cache_data(ttl=300)
def read_report(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


@st.cache_data(ttl=300)
def parse_latest_report(reports_dir: str = "reports") -> tuple[list[dict], list[dict]]:
    """Parse the most recent report for top picks and exploitable markets table.

    Returns (top_picks, table_picks).
    """
    reports = list_reports(reports_dir)
    if not reports:
        return [], []

    content = read_report(reports[0][1])
    if not content:
        return [], []

    # Parse top 3 detailed picks
    top_picks = []
    pick_pattern = re.compile(
        r'### #(\d+)\s+BET (YES|NO)\s*\n'
        r'\*\*(.+?)\*\*\s*\n'
        r'.*?Current YES price:\*\*\s*\$(\d+\.?\d*)'
        r'.*?Edge:\*\*\s*(\d+\.?\d*)'
        r'.*?Confidence:\*\*\s*(\d+\.?\d*)'
        r'.*?Madness Ratio:\*\*\s*(\d+\.?\d*)'
        r'.*?Bets Analyzed:\*\*\s*(\d+)',
        re.DOTALL,
    )
    for match in pick_pattern.finditer(content):
        top_picks.append({
            "rank": int(match.group(1)),
            "side": match.group(2),
            "title": match.group(3),
            "yes_price": float(match.group(4)),
            "edge": float(match.group(5)),
            "confidence": float(match.group(6)),
            "madness": float(match.group(7)),
            "n_bets": int(match.group(8)),
        })

    # Parse table rows
    table_picks = []
    table_pattern = re.compile(
        r'\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*BET (YES|NO)\s*\|\s*\$(\d+\.?\d*)\s*\|\s*'
        r'(\d+\.?\d*)\s*\|\s*(\d+\.?\d*)\s*\|\s*(\d+\.?\d*)\s*\|'
    )
    for match in table_pattern.finditer(content):
        table_picks.append({
            "rank": int(match.group(1)),
            "title": match.group(2).strip(),
            "side": match.group(3),
            "buy_at": float(match.group(4)),
            "edge": float(match.group(5)),
            "confidence": float(match.group(6)),
            "madness": float(match.group(7)),
        })

    return top_picks, table_picks
