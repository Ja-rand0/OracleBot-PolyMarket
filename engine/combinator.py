"""Brute-force combination testing — Tier 1, 2, 3."""
from __future__ import annotations

import logging
import sqlite3
from itertools import combinations

import config
from data import db
from data.models import Bet, ComboResults, Market, Wallet
from engine.backtest import backtest_combo
from methods import CATEGORIES, get_methods_by_category

log = logging.getLogger(__name__)

# Cap combo sizes to prevent combinatorial explosion
MAX_TIER1_COMBO_SIZE = 3   # within-category: singles, pairs, triples
MAX_TIER2_COMBO_SIZE = 3   # cross-category: pairs and triples of finalists
MAX_TIER3_SEEDS = 3        # hill-climb only the top 3


def _sized_combos(method_ids: list[str], max_size: int) -> list[list[str]]:
    """Generate combos from size 1..max_size."""
    result = []
    for r in range(1, min(max_size, len(method_ids)) + 1):
        for combo in combinations(method_ids, r):
            result.append(list(combo))
    return result


def tier1(
    conn: sqlite3.Connection,
    markets: list[Market],
    bets_by_market: dict[str, list[Bet]],
    wallets: dict[str, Wallet],
) -> dict[str, list[ComboResults]]:
    """Tier 1: test within-category combinations (up to triples)."""
    category_results: dict[str, list[ComboResults]] = {}

    for cat_name, method_ids in CATEGORIES.items():
        available = [mid for mid in method_ids if mid in {
            m for m in get_methods_by_category(cat_name)
        }]
        if not available:
            log.warning("No methods registered for category %s", cat_name)
            continue

        combos = _sized_combos(available, MAX_TIER1_COMBO_SIZE)
        log.info("Tier 1 — %s: %d combos from %d methods",
                 cat_name, len(combos), len(available))

        results: list[ComboResults] = []
        for combo in combos:
            cr = backtest_combo(combo, markets, bets_by_market, wallets)
            db.insert_method_result(conn, cr)
            results.append(cr)

        results.sort(key=lambda r: r.fitness_score, reverse=True)
        top = results[:config.TIER1_TOP_PER_CATEGORY]
        category_results[cat_name] = top

        for i, cr in enumerate(top):
            log.info("  Tier 1 %s #%d: %s (fitness=%.4f)", cat_name, i + 1,
                     cr.combo_id, cr.fitness_score)

    return category_results


def tier2(
    conn: sqlite3.Connection,
    tier1_results: dict[str, list[ComboResults]],
    markets: list[Market],
    bets_by_market: dict[str, list[Bet]],
    wallets: dict[str, Wallet],
) -> list[ComboResults]:
    """Tier 2: cross-category pairs and triples of Tier 1 finalists."""

    finalists: list[list[str]] = []
    for cat_results in tier1_results.values():
        for cr in cat_results:
            finalists.append(cr.methods_used)

    if not finalists:
        log.warning("No Tier 1 finalists — skipping Tier 2")
        return []

    # Only pairs and triples — NOT all 2^N subsets
    all_combos: list[list[str]] = []
    for r in range(2, min(MAX_TIER2_COMBO_SIZE + 1, len(finalists) + 1)):
        for subset in combinations(range(len(finalists)), r):
            merged: list[str] = []
            for idx in subset:
                merged.extend(finalists[idx])
            seen: set[str] = set()
            unique: list[str] = []
            for m in merged:
                if m not in seen:
                    seen.add(m)
                    unique.append(m)
            all_combos.append(unique)

    log.info("Tier 2: testing %d combos from %d finalists",
             len(all_combos), len(finalists))

    results: list[ComboResults] = []
    for i, combo in enumerate(all_combos):
        if (i + 1) % 100 == 0:
            log.info("  Tier 2 progress: %d / %d", i + 1, len(all_combos))
        cr = backtest_combo(combo, markets, bets_by_market, wallets)
        db.insert_method_result(conn, cr)
        results.append(cr)

    results.sort(key=lambda r: r.fitness_score, reverse=True)
    top = results[:config.TIER2_TOP_OVERALL]

    for i, cr in enumerate(top):
        log.info("  Tier 2 #%d: %s (fitness=%.4f)", i + 1, cr.combo_id, cr.fitness_score)

    return top


def tier3(
    conn: sqlite3.Connection,
    tier2_top: list[ComboResults],
    all_method_ids: list[str],
    markets: list[Market],
    bets_by_market: dict[str, list[Bet]],
    wallets: dict[str, Wallet],
) -> list[ComboResults]:
    """Tier 3: hill-climbing on the top few combos."""

    refined: list[ComboResults] = []

    for cr in tier2_top[:MAX_TIER3_SEEDS]:
        current = list(cr.methods_used)
        current_fitness = cr.fitness_score
        improved = True

        while improved:
            improved = False

            # Try adding each unused method
            unused = [m for m in all_method_ids if m not in current]
            for method in unused:
                candidate = current + [method]
                result = backtest_combo(candidate, markets, bets_by_market, wallets)
                if result.fitness_score > current_fitness:
                    current = candidate
                    current_fitness = result.fitness_score
                    improved = True
                    log.info("  Tier 3 +%s -> fitness=%.4f", method, current_fitness)
                    db.insert_method_result(conn, result)
                    break

            if improved:
                continue

            # Try removing each included method
            if len(current) > 1:
                for method in list(current):
                    candidate = [m for m in current if m != method]
                    result = backtest_combo(candidate, markets, bets_by_market, wallets)
                    if result.fitness_score > current_fitness:
                        current = candidate
                        current_fitness = result.fitness_score
                        improved = True
                        log.info("  Tier 3 -%s -> fitness=%.4f", method, current_fitness)
                        db.insert_method_result(conn, result)
                        break

        final = backtest_combo(current, markets, bets_by_market, wallets)
        db.insert_method_result(conn, final)
        refined.append(final)
        log.info("Tier 3 refined: %s (fitness=%.4f)", final.combo_id, final.fitness_score)

    refined.sort(key=lambda r: r.fitness_score, reverse=True)
    return refined


def run_full_optimization(
    conn: sqlite3.Connection,
    markets: list[Market],
    bets_by_market: dict[str, list[Bet]],
    wallets: dict[str, Wallet],
) -> list[ComboResults]:
    """Run the complete Tier 1 -> 2 -> 3 optimization pipeline."""
    from methods import get_all_method_ids

    log.info("=== Starting full optimization ===")

    t1 = tier1(conn, markets, bets_by_market, wallets)
    db.flush_method_results(conn)

    t2 = tier2(conn, t1, markets, bets_by_market, wallets)
    db.flush_method_results(conn)

    t3 = tier3(conn, t2, get_all_method_ids(), markets, bets_by_market, wallets)
    db.flush_method_results(conn)

    # Keep only the top 50 results, delete the rest
    pruned = db.prune_method_results(conn, keep=50)
    if pruned:
        log.info("Pruned %d old method results", pruned)

    log.info("=== Optimization complete — top combo: %s (fitness=%.4f) ===",
             t3[0].combo_id if t3 else "none", t3[0].fitness_score if t3 else 0)

    return t3
