"""Entry point — data collection loop, analysis, and reporting."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime

import schedule

import config
from data import db
from data.models import Bet, Wallet
from data.scraper import fetch_markets, fetch_resolved_markets, fetch_trades_for_market
from engine.combinator import run_full_optimization
from engine.report import generate_report

log = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Wallet stats computation
# ---------------------------------------------------------------------------
def update_wallet_stats(conn) -> dict[str, Wallet]:
    """Recompute wallet statistics from bet history."""
    all_wallets: dict[str, Wallet] = db.get_all_wallets(conn)
    resolved_markets = db.get_all_markets(conn, resolved_only=True)
    resolved_ids = {m.id: m for m in resolved_markets}

    # Gather all bets per wallet
    wallet_bets: dict[str, list[Bet]] = defaultdict(list)
    for market in resolved_markets:
        for bet in db.get_bets_for_market(conn, market.id):
            wallet_bets[bet.wallet].append(bet)

    for addr, bets in wallet_bets.items():
        wins = 0
        total_resolved = 0
        total_volume = sum(b.amount for b in bets)

        for b in bets:
            m = resolved_ids.get(b.market_id)
            if m and m.outcome:
                total_resolved += 1
                if b.side == m.outcome:
                    wins += 1

        win_rate = wins / total_resolved if total_resolved > 0 else 0.0

        # Rationality heuristic: combination of win rate, bet precision, odds sensitivity
        round_bets = sum(1 for b in bets if b.amount >= 50 and b.amount % 50 == 0)
        round_ratio = round_bets / len(bets) if bets else 0.0
        rationality = max(0.0, min(1.0, win_rate * 0.5 + (1 - round_ratio) * 0.3 + 0.2))

        w = all_wallets.get(addr, Wallet(address=addr))
        w.total_bets = len(bets)
        w.total_volume = total_volume
        w.win_rate = win_rate
        w.rationality_score = rationality
        w.first_seen = min(b.timestamp for b in bets) if bets else w.first_seen

        db.upsert_wallet(conn, w)
        all_wallets[addr] = w

    log.info("Updated stats for %d wallets", len(wallet_bets))
    return all_wallets


# ---------------------------------------------------------------------------
# Data collection cycle
# ---------------------------------------------------------------------------
def collect_data(conn) -> None:
    """Fetch markets and trades, store in DB."""
    log.info("=== Starting data collection cycle ===")

    # Fetch active markets
    markets = fetch_markets(active_only=True)
    for m in markets:
        db.upsert_market(conn, m)
    log.info("Stored %d active markets", len(markets))

    # Fetch trades for each market
    total_trades = 0
    markets_with_trades = 0
    for i, m in enumerate(markets):
        if (i + 1) % 100 == 0:
            log.info("  Trade fetch progress: %d / %d markets", i + 1, len(markets))
        try:
            since = db.get_latest_bet_timestamp(conn, m.id)
            trades = fetch_trades_for_market(m.id, since=since)
            if trades:
                inserted = db.insert_bets_bulk(conn, trades)
                total_trades += inserted
                markets_with_trades += 1
        except Exception:
            log.exception("Failed to fetch trades for market %s", m.id[:16])

    log.info("Collected %d new trades from %d markets (of %d total)",
             total_trades, markets_with_trades, len(markets))

    # Also fetch recently resolved markets for backtesting data
    resolved = fetch_resolved_markets(max_pages=5)
    for m in resolved:
        db.upsert_market(conn, m)
    log.info("Stored %d resolved markets", len(resolved))

    for m in resolved:
        try:
            since = db.get_latest_bet_timestamp(conn, m.id)
            trades = fetch_trades_for_market(m.id, since=since)
            if trades:
                db.insert_bets_bulk(conn, trades)
        except Exception:
            log.exception("Failed to fetch trades for resolved market %s", m.id[:16])

    log.info("=== Data collection complete ===")


# ---------------------------------------------------------------------------
# Analysis cycle
# ---------------------------------------------------------------------------
def run_analysis(conn) -> None:
    """Run the full analysis pipeline: update wallets, run combinator, generate report."""
    log.info("=== Starting analysis cycle ===")

    wallets = update_wallet_stats(conn)

    # Gather data for backtesting
    resolved_markets = db.get_all_markets(conn, resolved_only=True)
    all_markets = db.get_all_markets(conn)

    bets_by_market: dict[str, list[Bet]] = {}
    for m in all_markets:
        bets_by_market[m.id] = db.get_bets_for_market(conn, m.id)

    if len(resolved_markets) >= 10:
        log.info("Running optimization on %d resolved markets", len(resolved_markets))
        run_full_optimization(conn, resolved_markets, bets_by_market, wallets)
    else:
        log.warning("Only %d resolved markets — need at least 10 for optimization",
                     len(resolved_markets))

    # Generate daily report on active markets
    active_markets = [m for m in all_markets if not m.resolved]
    generate_report(conn, active_markets, bets_by_market, wallets)

    log.info("=== Analysis complete ===")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Polymarket Prediction Bot (read-only)")
    parser.add_argument("command", choices=["collect", "analyze", "run", "init"],
                        help="collect=fetch data, analyze=run analysis, "
                             "run=continuous loop, init=create DB only")
    parser.add_argument("--db", default=config.DB_PATH, help="SQLite database path")
    args = parser.parse_args()

    config.DB_PATH = args.db
    conn = db.get_connection()
    db.init_db(conn)

    if args.command == "init":
        log.info("Database initialised at %s", args.db)
        return

    if args.command == "collect":
        collect_data(conn)
        return

    if args.command == "analyze":
        run_analysis(conn)
        return

    if args.command == "run":
        log.info("Starting continuous loop (every %d minutes)", config.SCRAPE_INTERVAL_MINUTES)

        def cycle():
            try:
                collect_data(conn)
                run_analysis(conn)
            except Exception:
                log.exception("Cycle failed — will retry next interval")

        # Run once immediately
        cycle()

        # Schedule recurring
        schedule.every(config.SCRAPE_INTERVAL_MINUTES).minutes.do(cycle)

        while True:
            schedule.run_pending()
            time.sleep(30)


if __name__ == "__main__":
    main()
