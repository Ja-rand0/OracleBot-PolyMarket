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
) -> str:
    """Generate a daily markdown report and return the content."""

    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Get best combo
    top_combos = db.get_top_combos(conn, limit=5)
    best_methods = top_combos[0].methods_used if top_combos else []

    lines = [
        f"# Polymarket Bot — Daily Report ({today})",
        "",
    ]

    # --- Top Exploitable Markets ---
    lines.append("## Top Exploitable Markets (High Madness Ratio)")
    lines.append("")
    lines.append("| Market | Madness Ratio | Smart Money Side | Confidence |")
    lines.append("|--------|---------------|------------------|------------|")

    market_scores: list[tuple[Market, float, float, float]] = []

    for market in markets:
        if market.resolved:
            continue
        market_bets = bets_by_market.get(market.id, [])
        if len(market_bets) < 5:
            continue

        signal, confidence, meta = _run_best_combo(best_methods, market, market_bets, wallets)
        emotion_ratio = meta.get("emotion_ratio", 0.0)
        market_scores.append((market, emotion_ratio, signal, confidence))

    market_scores.sort(key=lambda x: x[1], reverse=True)

    for market, ratio, signal, confidence in market_scores[:15]:
        side = "YES" if signal > 0 else "NO" if signal < 0 else "—"
        title = market.title[:60]
        lines.append(f"| {title} | {ratio:.2f} | {side} ({abs(signal):.2f}) | {confidence:.2f} |")

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
    filepath = os.path.join(output_dir, f"report_{today}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    log.info("Report written to %s", filepath)

    # Also print to console
    print(report)

    return report
