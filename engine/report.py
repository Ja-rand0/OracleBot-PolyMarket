"""Daily report generation."""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime

import numpy as np

import config
from data import db
from data.models import Bet, Market, MethodResult, Wallet
from methods import get_method

log = logging.getLogger(__name__)


def _run_best_combo(
    combo_methods: list[str],
    market: Market,
    bets: list[Bet],
    wallets: dict[str, Wallet],
) -> tuple[float, float, dict]:
    """Run the best combo on a single market, return signal, confidence, metadata."""
    results: list[MethodResult] = []
    current_bets = bets

    for method_id in combo_methods:
        try:
            fn = get_method(method_id)
            result = fn(market, current_bets, wallets)
            results.append(result)
            if result.filtered_bets:
                current_bets = result.filtered_bets
        except Exception:
            log.exception("Method %s failed on market %s", method_id, market.id[:16])

    if not results:
        return 0.0, 0.0, {}

    total_w = sum(r.confidence for r in results)
    if total_w == 0:
        return 0.0, 0.0, {}

    signal = sum(r.signal * r.confidence for r in results) / total_w
    confidence = total_w / len(results)

    # Emotion ratio for P24 / wisdom-madness
    emotional_count = sum(1 for b in bets if (wallets.get(b.wallet) or Wallet(address="")).rationality_score < 0.4)
    emotion_ratio = emotional_count / len(bets) if bets else 0.0

    return (
        max(-1.0, min(1.0, signal)),
        min(1.0, confidence),
        {"emotion_ratio": emotion_ratio},
    )


def generate_report(
    conn: sqlite3.Connection,
    markets: list[Market],
    bets_by_market: dict[str, list[Bet]],
    wallets: dict[str, Wallet],
    output_dir: str = ".",
) -> tuple[str, list[tuple]]:
    """Generate a daily markdown report.

    Returns (report_text, scored_markets) where scored_markets is a list of
    (Market, emotion_ratio, signal, confidence, n_bets) sorted by conviction."""

    today = datetime.utcnow().strftime("%Y-%m-%d")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M")

    # Get best combo
    top_combos = db.get_top_combos(conn, limit=5)
    best_methods = top_combos[0].methods_used if top_combos else []

    lines = [
        f"# OracleBot — Daily Report ({today})",
        "",
    ]

    # --- Score all markets ---
    # Each entry: (Market, emotion_ratio, signal, confidence, n_bets, market_price)
    market_scores: list[tuple[Market, float, float, float, int, float]] = []

    for market in markets:
        if market.resolved:
            continue
        market_bets = bets_by_market.get(market.id, [])
        if len(market_bets) < 5:
            continue

        # Only pass wallets relevant to this market
        mw = {b.wallet: wallets[b.wallet] for b in market_bets if b.wallet in wallets}
        signal, confidence, meta = _run_best_combo(best_methods, market, market_bets, mw)
        emotion_ratio = meta.get("emotion_ratio", 0.0)

        # Current market price (YES probability) from recent trades.
        # Volume-weighted average reduces noise from small trades on thin markets.
        recent = sorted(market_bets, key=lambda b: b.timestamp)[-config.REPORT_PRICE_RECENT_TRADES:]
        if len(recent) >= config.REPORT_PRICE_MIN_TRADES:
            total_vol = sum(b.amount for b in recent)
            if total_vol > 0:
                market_price = sum(
                    (b.odds if b.side == "YES" else (1 - b.odds)) * b.amount
                    for b in recent
                ) / total_vol
            else:
                market_price = 0.5
        else:
            market_price = 0.5

        market_scores.append((market, emotion_ratio, signal, confidence, len(market_bets), market_price))

    # Filter out markets at extreme prices — these are essentially settled
    # and the bot has no real information to disagree with.
    market_scores = [
        m for m in market_scores if 0.05 < m[5] < 0.95
    ]

    # Rank by edge: how much the bot disagrees with the market price.
    # If market says 50% YES and bot says strong YES (signal=0.8), edge is high.
    # If market says 95% NO and bot also says NO, there's no edge (market agrees).
    def _edge_score(entry):
        _market, _ratio, signal, confidence, _n, price = entry
        # Bot's implied probability: signal > 0 means YES, mapped to 0.5–1.0
        bot_prob = 0.5 + signal * 0.5   # signal=+1 → 1.0, signal=-1 → 0.0
        # Edge = how far bot diverges from market, weighted by confidence
        return abs(bot_prob - price) * confidence

    market_scores.sort(key=_edge_score, reverse=True)

    # Drop markets where the bot has no meaningful edge
    market_scores = [m for m in market_scores if _edge_score(m) > 0.01]

    # --- TOP 3 PICKS ---
    lines.append("## TOP 3 PICKS")
    lines.append("")
    if not market_scores:
        lines.append("*No high-conviction picks yet — need more data or resolved combos.*")
        lines.append("")
    for i, (market, ratio, signal, confidence, n_bets, price) in enumerate(market_scores[:3]):
        side = "YES" if signal > 0 else "NO"
        buy_price = price if signal > 0 else (1 - price)
        bot_prob = 0.5 + signal * 0.5
        edge = abs(bot_prob - price) * confidence
        lines.append(f"### #{i+1}  BET {side}")
        lines.append(f"**{market.title}**")
        lines.append(f"")
        lines.append(f"- **Action:** Buy **{side}** shares")
        lines.append(f"- **Current YES price:** ${price:.2f}  |  **Current NO price:** ${1-price:.2f}")
        lines.append(f"- **You buy at:** ${buy_price:.2f}  |  **Pays:** $1.00 if correct")
        lines.append(f"- **Bot says:** {bot_prob:.0%} YES  vs  market {price:.0%}  |  **Edge:** {edge:.2f}")
        lines.append(f"- **Confidence:** {confidence:.2f}  |  **Madness Ratio:** {ratio:.2f}  |  **Bets Analyzed:** {n_bets}")
        if market.description:
            desc = market.description[:200].replace("\n", " ")
            lines.append(f"- **Details:** {desc}")
        lines.append("")

    # --- All Exploitable Markets ---
    lines.append("## All Exploitable Markets")
    lines.append("")
    lines.append("| # | Market | Action | Buy At | Edge | Conf | Madness |")
    lines.append("|---|--------|--------|--------|------|------|---------|")

    for i, (market, ratio, signal, confidence, n_bets, price) in enumerate(market_scores[:20]):
        side = "YES" if signal > 0 else "NO" if signal < 0 else "—"
        buy_price = price if signal > 0 else (1 - price) if signal < 0 else 0
        bot_prob = 0.5 + signal * 0.5
        edge = abs(bot_prob - price) * confidence
        title = market.title[:50]
        lines.append(
            f"| {i+1} | {title} | BET {side} | ${buy_price:.2f} | "
            f"{edge:.2f} | {confidence:.2f} | {ratio:.2f} |"
        )

    lines.append("")

    # --- Suspicious Wallet Activity ---
    lines.append("## Suspicious Wallet Activity")
    lines.append("")
    lines.append("| Wallet | Win Rate | Total Bets | Volume | Flagged |")
    lines.append("|--------|----------|------------|--------|---------|")

    suspicious = [
        w for w in wallets.values()
        if w.flagged_suspicious and w.total_bets >= 10
    ]
    suspicious.sort(key=lambda w: w.win_rate, reverse=True)

    for w in suspicious[:20]:
        lines.append(
            f"| {w.address[:12]}... | {w.win_rate:.2%} | {w.total_bets} | "
            f"${w.total_volume:,.0f} | Suspicious |"
        )

    lines.append("")

    # --- Sandpit Alerts ---
    lines.append("## Sandpit Alerts (Wallets to Avoid)")
    lines.append("")
    lines.append("| Wallet | Total Bets | Win Rate | Volume |")
    lines.append("|--------|------------|----------|--------|")

    sandpits = [w for w in wallets.values() if w.flagged_sandpit]
    for w in sandpits[:10]:
        lines.append(
            f"| {w.address[:12]}... | {w.total_bets} | {w.win_rate:.2%} | "
            f"${w.total_volume:,.0f} |"
        )

    lines.append("")

    # --- Method Combo Performance ---
    lines.append("## Method Combo Performance")
    lines.append("")
    lines.append("| Combo | Accuracy | Edge | FPR | Fitness |")
    lines.append("|-------|----------|------|-----|---------|")

    for cr in top_combos:
        lines.append(
            f"| {cr.combo_id} | {cr.accuracy:.2%} | {cr.edge_vs_market:.3f} | "
            f"{cr.false_positive_rate:.2%} | {cr.fitness_score:.4f} |"
        )

    lines.append("")

    report = "\n".join(lines)

    # Write to file
    filepath = os.path.join(output_dir, f"report_{timestamp}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    log.info("Report written to %s", filepath)
    return report, market_scores
