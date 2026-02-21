"""Reusable UI components and constants for the OracleBot Streamlit dashboard."""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Color scheme (matches CLAUDE.md spec)
# ---------------------------------------------------------------------------
COLORS = {
    "yes": "#22c55e",
    "no": "#ef4444",
    "neutral": "#6b7280",
    "emotional": "#f59e0b",
    "rational": "#3b82f6",
    "suspicious": "#a855f7",
    "sandpit": "#dc2626",
    "cat_S": "#a855f7",
    "cat_D": "#3b82f6",
    "cat_E": "#f59e0b",
    "cat_T": "#22c55e",
    "cat_P": "#ec4899",
    "cat_M": "#06b6d4",
}

CATEGORY_NAMES = {
    "S": "Suspicious",
    "D": "Discrete",
    "E": "Emotional",
    "T": "Statistical",
    "P": "Psychological",
    "M": "Markov",
}

# ---------------------------------------------------------------------------
# Method metadata (hardcoded to avoid importing methods/ which triggers
# heavy deps like networkx, scipy, and method registration side-effects)
# ---------------------------------------------------------------------------
METHOD_INFO: dict[str, tuple[str, str]] = {
    "S1": ("S", "Win rate outlier detection"),
    "S2": ("S", "Bet timing analysis"),
    "S3": ("S", "Coordination clustering"),
    "S4": ("S", "Sandpit filter"),
    "D5": ("D", "Vacuous truth / implication logic"),
    "D6": ("D", "PageRank wallet influence"),
    "D7": ("D", "Pigeonhole noise filtering"),
    "D8": ("D", "Boolean SAT structure analysis"),
    "D9": ("D", "Set partition (clean vs noise)"),
    "E10": ("E", "Loyalty bias detection"),
    "E11": ("E", "Recency bias detection"),
    "E12": ("E", "Revenge betting patterns"),
    "E13": ("E", "Hype/media spike detection"),
    "E14": ("E", "Odds sensitivity scoring"),
    "E15": ("E", "Round number detection"),
    "E16": ("E", "KL divergence bias"),
    "T17": ("T", "Bayesian updating"),
    "T18": ("T", "Benford's Law analysis"),
    "T19": ("T", "Z-score outlier detection"),
    "P20": ("P", "Nash equilibrium deviation"),
    "P21": ("P", "Prospect theory exploitation"),
    "P22": ("P", "Herding behavior detection"),
    "P23": ("P", "Anchoring bias tracking"),
    "P24": ("P", "Wisdom vs madness ratio"),
    "M25": ("M", "Wallet bet-size escalation"),
    "M26": ("M", "Market phase transitions"),
    "M27": ("M", "Bet flow momentum"),
    "M28": ("M", "Smart-follow sequencing"),
}


def category_color(category: str) -> str:
    return COLORS.get(f"cat_{category}", COLORS["neutral"])


def side_color(side: str) -> str:
    if side == "YES":
        return COLORS["yes"]
    if side == "NO":
        return COLORS["no"]
    return COLORS["neutral"]


def side_badge_html(signal: float) -> str:
    if signal > 0:
        return f'<span style="color:{COLORS["yes"]};font-weight:bold">BET YES</span>'
    elif signal < 0:
        return f'<span style="color:{COLORS["no"]};font-weight:bold">BET NO</span>'
    return f'<span style="color:{COLORS["neutral"]}">NEUTRAL</span>'


def wallet_flags_html(suspicious: bool, sandpit: bool) -> str:
    parts = []
    if suspicious:
        parts.append(f'<span style="background:{COLORS["suspicious"]};color:white;padding:2px 6px;border-radius:4px;font-size:0.8em">Suspicious</span>')
    if sandpit:
        parts.append(f'<span style="background:{COLORS["sandpit"]};color:white;padding:2px 6px;border-radius:4px;font-size:0.8em">Sandpit</span>')
    if not parts:
        return '<span style="color:#6b7280;font-size:0.8em">Clean</span>'
    return " ".join(parts)


def method_badges_html(methods: list[str]) -> str:
    parts = []
    for m in methods:
        cat = METHOD_INFO.get(m, ("?", ""))[0]
        color = category_color(cat)
        parts.append(f'<span style="background:{color};color:white;padding:1px 5px;border-radius:3px;font-size:0.8em;margin-right:2px">{m}</span>')
    return " ".join(parts)


def render_pick_card(rank: int, title: str, side: str, yes_price: float,
                     edge: float, confidence: float, madness: float,
                     n_bets: int, description: str = ""):
    border_color = COLORS["yes"] if side == "YES" else COLORS["no"]
    side_col = COLORS["yes"] if side == "YES" else COLORS["no"]
    buy_price = yes_price if side == "YES" else (1 - yes_price)
    bot_prob = (yes_price + edge / max(confidence, 0.01)) if side == "YES" else (yes_price - edge / max(confidence, 0.01))
    bot_prob = max(0, min(1, bot_prob))

    st.markdown(
        f"""<div style="border:2px solid {border_color};border-radius:8px;padding:16px;margin-bottom:12px">
        <h4 style="margin:0">Pick #{rank} — <span style="color:{side_col}">BET {side}</span></h4>
        <p style="font-size:1.1em;margin:4px 0 8px 0"><strong>{title}</strong></p>
        <table style="width:100%;border-collapse:collapse">
        <tr><td style="color:#9ca3af;padding:2px 0">YES price</td><td><strong>${yes_price:.2f}</strong></td>
            <td style="color:#9ca3af">NO price</td><td><strong>${1-yes_price:.2f}</strong></td></tr>
        <tr><td style="color:#9ca3af;padding:2px 0">Buy at</td><td><strong>${buy_price:.2f}</strong> → pays <strong>$1.00</strong></td>
            <td style="color:#9ca3af">Edge</td><td style="color:#eab308"><strong>{edge:.2f}</strong></td></tr>
        <tr><td style="color:#9ca3af;padding:2px 0">Confidence</td><td>{confidence:.2f}</td>
            <td style="color:#9ca3af">Madness</td><td>{madness:.2f}</td></tr>
        <tr><td style="color:#9ca3af;padding:2px 0">Bets analyzed</td><td>{n_bets}</td>
            <td></td><td></td></tr>
        </table>
        {"<p style='color:#9ca3af;font-size:0.85em;margin-top:6px'>" + description[:200] + "</p>" if description else ""}
        </div>""",
        unsafe_allow_html=True,
    )
