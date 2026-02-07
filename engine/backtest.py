"""Backtesting framework — replay resolved markets through method combos."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np

import config
from data.models import Bet, ComboResults, Market, MethodResult, Wallet
from engine.fitness import calculate_fitness
from methods import get_method

log = logging.getLogger(__name__)


def _aggregate_signals(results: list[MethodResult]) -> tuple[float, float]:
    """Combine multiple method results into a single signal + confidence.
    Weighted average by confidence."""
    if not results:
        return 0.0, 0.0

    total_weight = sum(r.confidence for r in results)
    if total_weight == 0:
        return 0.0, 0.0

    signal = sum(r.signal * r.confidence for r in results) / total_weight
    confidence = total_weight / len(results)
    return max(-1.0, min(1.0, signal)), min(1.0, confidence)


def backtest_combo(
    combo: list[str],
    markets: list[Market],
    bets_by_market: dict[str, list[Bet]],
    wallets: dict[str, Wallet],
    cutoff_fraction: float = config.BACKTEST_CUTOFF_FRACTION,
) -> ComboResults:
    """Run a method combo against historical resolved markets.

    For each resolved market:
    1. Take bets up to cutoff_fraction of the market lifespan
    2. Run each method in the combo
    3. Aggregate signals
    4. Compare predicted side to actual outcome
    """
    correct = 0
    total_markets = 0
    edge_sum = 0.0
    false_positives = 0
    high_confidence_preds = 0

    for market in markets:
        if not market.resolved or market.outcome is None:
            continue

        market_bets = bets_by_market.get(market.id, [])
        if len(market_bets) < 5:
            continue

        # Apply cutoff: only use bets from the first X% of the market lifespan
        lifespan = (market.end_date - market.created_at).total_seconds()
        if lifespan <= 0:
            continue

        cutoff_time = market.created_at + timedelta(seconds=lifespan * cutoff_fraction)
        visible_bets = [b for b in market_bets if b.timestamp <= cutoff_time]

        if len(visible_bets) < 3:
            continue

        # Run each method
        results: list[MethodResult] = []
        current_bets = visible_bets
        for method_id in combo:
            try:
                fn = get_method(method_id)
                result = fn(market, current_bets, wallets)
                results.append(result)
                # Methods that filter bets pass their filtered set forward
                if result.filtered_bets:
                    current_bets = result.filtered_bets
            except Exception:
                log.exception("Method %s failed on market %s", method_id, market.id[:16])

        if not results:
            continue

        signal, confidence = _aggregate_signals(results)
        total_markets += 1

        # Prediction
        predicted = "YES" if signal > 0 else "NO"
        actual = market.outcome

        if predicted == actual:
            correct += 1
        elif confidence > 0.5:
            false_positives += 1

        if confidence > 0.5:
            high_confidence_preds += 1

        # Edge: compare our confidence with market odds at cutoff
        market_odds = float(np.median([b.odds for b in visible_bets]))
        market_implied = "YES" if market_odds > 0.5 else "NO"
        if predicted == actual and market_implied != actual:
            edge_sum += abs(signal)

    accuracy = correct / total_markets if total_markets > 0 else 0.0
    edge = edge_sum / total_markets if total_markets > 0 else 0.0
    fpr = false_positives / high_confidence_preds if high_confidence_preds > 0 else 0.0

    combo_id = ",".join(combo)
    cr = ComboResults(
        combo_id=combo_id,
        methods_used=combo,
        accuracy=accuracy,
        edge_vs_market=edge,
        false_positive_rate=fpr,
        complexity=len(combo),
        tested_at=datetime.utcnow(),
    )
    cr.fitness_score = calculate_fitness(cr)

    log.info("Combo %s: accuracy=%.3f edge=%.3f fpr=%.3f fitness=%.4f (n=%d)",
             combo_id, accuracy, edge, fpr, cr.fitness_score, total_markets)

    return cr
