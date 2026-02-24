"""Backtesting framework — replay resolved markets through method combos."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from statistics import median

import config
from data.models import Bet, ComboResults, Market, MethodResult, Wallet
from engine.fitness import calculate_fitness
from methods import get_method

log = logging.getLogger(__name__)

# Cap bets per market to avoid O(n²) explosions in graph-based methods
MAX_BETS_PER_MARKET = 500


def _aggregate_signals(results: list[MethodResult]) -> tuple[float, float]:
    """Combine multiple method results into a single signal + confidence."""
    if not results:
        return 0.0, 0.0

    total_weight = sum(r.confidence for r in results)
    if total_weight == 0:
        return 0.0, 0.0

    signal = sum(r.signal * r.confidence for r in results) / total_weight
    confidence = total_weight / len(results)
    return max(-1.0, min(1.0, signal)), min(1.0, confidence)


def split_holdout(
    markets: list[Market],
    holdout_fraction: float,
) -> tuple[list[Market], list[Market]]:
    """Temporally split markets: oldest → train, newest → holdout.
    Returns (train_markets, holdout_markets)."""
    if not markets:
        return [], []
    sorted_markets = sorted(markets, key=lambda m: m.created_at)
    split_idx = int(len(sorted_markets) * (1 - holdout_fraction))
    return sorted_markets[:split_idx], sorted_markets[split_idx:]


def backtest_combo(
    combo: list[str],
    markets: list[Market],
    bets_by_market: dict[str, list[Bet]],
    wallets: dict[str, Wallet],
    cutoff_fraction: float = config.BACKTEST_CUTOFF_FRACTION,
) -> ComboResults:
    """Run a method combo against historical resolved markets."""
    correct = 0
    total_markets = 0
    edge_sum = 0.0
    false_positives = 0
    high_confidence_preds = 0

    # Cache method function lookups once per combo
    method_fns = [(mid, get_method(mid)) for mid in combo]
    combo_id = ",".join(sorted(combo))

    for market in markets:
        if not market.resolved or market.outcome is None:
            continue

        market_bets = bets_by_market.get(market.id)
        if not market_bets or len(market_bets) < 5:
            continue

        lifespan = (market.end_date - market.created_at).total_seconds()
        if lifespan <= 0:
            continue

        cutoff_time = market.created_at + timedelta(seconds=lifespan * cutoff_fraction)
        visible_bets = [b for b in market_bets if b.timestamp <= cutoff_time]

        if len(visible_bets) < 3:
            continue

        # Cap bets: keep most recent N to avoid O(n²) in graph methods
        if len(visible_bets) > MAX_BETS_PER_MARKET:
            visible_bets = visible_bets[-MAX_BETS_PER_MARKET:]

        # Only pass wallets that appear in this market's bets (not all 139k)
        market_addrs = {b.wallet for b in visible_bets}
        market_wallets = {a: wallets[a] for a in market_addrs if a in wallets}

        # Run each method
        results: list[MethodResult] = []
        current_bets = visible_bets
        for method_id, fn in method_fns:
            try:
                result = fn(market, current_bets, market_wallets)
                results.append(result)
                if result.filtered_bets:
                    current_bets = result.filtered_bets
            except Exception:
                log.exception("Method %s failed on market %s", method_id, market.id[:16])

        if not results:
            continue

        signal, confidence = _aggregate_signals(results)
        total_markets += 1

        predicted = "YES" if signal > 0 else "NO"
        actual = market.outcome

        if predicted == actual:
            correct += 1
        elif confidence > 0.3:
            false_positives += 1

        if confidence > 0.3:
            high_confidence_preds += 1

        yes_probs = [b.odds for b in visible_bets]
        market_odds = median(yes_probs) if yes_probs else 0.5
        market_implied = "YES" if market_odds > 0.5 else "NO"
        if predicted == actual and market_implied != actual:
            edge_sum += abs(signal)

    accuracy = correct / total_markets if total_markets > 0 else 0.0
    edge = edge_sum / total_markets if total_markets > 0 else 0.0
    fpr = false_positives / high_confidence_preds if high_confidence_preds > 0 else 0.0

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
    return cr
