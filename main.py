"""Entry point — data collection loop, analysis, and reporting."""
from __future__ import annotations

import argparse
import gc
import logging
import time
from datetime import datetime

import schedule

import config
from data import db
from data.models import Bet, Wallet
from data.scraper import fetch_markets, fetch_resolved_markets, fetch_trades_for_market
from engine.combinator import run_full_optimization
from engine.report import generate_report

log = logging.getLogger("main")

# Max active markets to fetch trades for per cycle (avoid hammering API)
MAX_ACTIVE_TRADE_FETCHES = 500
# Max resolved markets to fetch trades for per cycle
MAX_RESOLVED_TRADE_FETCHES = 100
# Min bets for a resolved market to be useful in backtesting
MIN_BETS_FOR_BACKTEST = 5


# ---------------------------------------------------------------------------
# Wallet stats — computed in SQL, not Python
# ---------------------------------------------------------------------------
def update_wallet_stats(conn) -> dict[str, Wallet]:
    """Recompute wallet statistics using SQL aggregation (memory-safe)."""
    cur = conn.cursor()

    # Aggregate wins/losses/volume per wallet in a single SQL query
    cur.execute("""
        SELECT
            b.wallet,
            MIN(b.timestamp) AS first_seen,
            COUNT(*) AS total_bets,
            SUM(b.amount) AS total_volume,
            SUM(CASE WHEN m.outcome IS NOT NULL AND b.side = m.outcome THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN m.outcome IS NOT NULL THEN 1 ELSE 0 END) AS resolved_bets,
            SUM(CASE WHEN b.amount >= 50 AND CAST(b.amount AS INTEGER) % 50 = 0 THEN 1 ELSE 0 END) AS round_bets
        FROM bets b
        LEFT JOIN markets m ON b.market_id = m.id AND m.resolved = 1
        GROUP BY b.wallet
    """)

    wallets: dict[str, Wallet] = {}
    bulk_rows = []
    for row in cur.fetchall():
        addr = row[0]
        first_seen_str = row[1]
        total_bets = row[2]
        total_volume = row[3] or 0.0
        wins = row[4] or 0
        resolved_bets = row[5] or 0
        round_bets = row[6] or 0

        win_rate = wins / resolved_bets if resolved_bets > 0 else 0.0
        round_ratio = round_bets / total_bets if total_bets > 0 else 0.0
        rationality = max(0.0, min(1.0, win_rate * 0.5 + (1 - round_ratio) * 0.3 + 0.2))

        try:
            fs = datetime.strptime(first_seen_str, "%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            fs = datetime.utcnow()

        w = Wallet(
            address=addr,
            first_seen=fs,
            total_bets=total_bets,
            total_volume=total_volume,
            win_rate=win_rate,
            rationality_score=rationality,
        )
        wallets[addr] = w
        bulk_rows.append((
            w.address, fs.strftime("%Y-%m-%dT%H:%M:%SZ"),
            w.total_bets, w.total_volume,
            w.win_rate, w.rationality_score,
            w.flagged_suspicious, w.flagged_sandpit,
        ))

    conn.executemany(
        """
        INSERT INTO wallets (address, first_seen, total_bets, total_volume,
                             win_rate, rationality_score, flagged_suspicious, flagged_sandpit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(address) DO UPDATE SET
            total_bets=excluded.total_bets,
            total_volume=excluded.total_volume,
            win_rate=excluded.win_rate,
            rationality_score=excluded.rationality_score,
            flagged_suspicious=excluded.flagged_suspicious,
            flagged_sandpit=excluded.flagged_sandpit
        """,
        bulk_rows,
    )
    conn.commit()
    log.info("Updated stats for %d wallets", len(wallets))
    return wallets


# ---------------------------------------------------------------------------
# Data collection cycle
# ---------------------------------------------------------------------------
def collect_data(conn) -> None:
    """Fetch markets and trades, store in DB."""
    log.info("=== Starting data collection cycle ===")

    # Fetch active markets (metadata only — cheap)
    markets = fetch_markets(active_only=True)
    for m in markets:
        db.upsert_market(conn, m)
    log.info("Stored %d active markets", len(markets))

    # Fetch trades for a capped subset of active markets
    total_trades = 0
    markets_with_trades = 0
    fetched = 0
    for i, m in enumerate(markets):
        if fetched >= MAX_ACTIVE_TRADE_FETCHES:
            break
        if (i + 1) % 200 == 0:
            log.info("  Trade fetch progress: %d / %d markets (fetched %d)",
                     i + 1, len(markets), fetched)
        try:
            since = db.get_latest_bet_timestamp(conn, m.id)
            trades = fetch_trades_for_market(m.id, since=since)
            if trades:
                db.insert_bets_bulk(conn, trades)
                total_trades += len(trades)
                markets_with_trades += 1
            fetched += 1
        except Exception:
            log.exception("Failed to fetch trades for market %s", m.id[:16])

    log.info("Collected %d new trades from %d markets (fetched %d of %d)",
             total_trades, markets_with_trades, fetched, len(markets))

    # Fetch resolved markets for backtesting
    resolved = fetch_resolved_markets(max_pages=3)
    for m in resolved:
        db.upsert_market(conn, m)
    log.info("Stored %d resolved markets", len(resolved))

    resolved_fetched = 0
    for m in resolved:
        if resolved_fetched >= MAX_RESOLVED_TRADE_FETCHES:
            break
        try:
            since = db.get_latest_bet_timestamp(conn, m.id)
            trades = fetch_trades_for_market(m.id, since=since)
            if trades:
                db.insert_bets_bulk(conn, trades)
            resolved_fetched += 1
        except Exception:
            log.exception("Failed to fetch trades for resolved market %s", m.id[:16])

    log.info("=== Data collection complete ===")


# ---------------------------------------------------------------------------
# Analysis cycle
# ---------------------------------------------------------------------------
def _load_bets_for_markets(conn, markets: list) -> dict[str, list[Bet]]:
    """Load bets only for markets that have enough data. Returns dict."""
    bets_by_market: dict[str, list[Bet]] = {}
    for m in markets:
        bets = db.get_bets_for_market(conn, m.id)
        if len(bets) >= MIN_BETS_FOR_BACKTEST:
            bets_by_market[m.id] = bets
    return bets_by_market


def run_analysis(conn) -> None:
    """Run the full analysis pipeline: update wallets, run combinator, generate report."""
    log.info("=== Starting analysis cycle ===")

    wallets = update_wallet_stats(conn)

    # Only load resolved markets that actually have bet data (via SQL count)
    resolved_markets = db.get_all_markets(conn, resolved_only=True)

    # Load bets only for resolved markets with enough data
    resolved_bets = _load_bets_for_markets(conn, resolved_markets)
    usable_resolved = [m for m in resolved_markets if m.id in resolved_bets]
    log.info("Resolved markets with %d+ bets: %d", MIN_BETS_FOR_BACKTEST, len(usable_resolved))

    if len(usable_resolved) >= 10:
        log.info("Running optimization on %d resolved markets", len(usable_resolved))
        run_full_optimization(conn, usable_resolved, resolved_bets, wallets)
    else:
        log.warning("Only %d usable resolved markets — need 10+ for optimization",
                     len(usable_resolved))

    # Free resolved data before loading active data
    del resolved_bets
    del resolved_markets
    gc.collect()

    # Generate daily report — only load active markets with data
    active_markets = db.get_all_markets(conn, resolved_only=False)
    active_markets = [m for m in active_markets if not m.resolved]
    active_bets = _load_bets_for_markets(conn, active_markets[:200])  # cap for report
    active_with_data = [m for m in active_markets if m.id in active_bets]

    generate_report(conn, active_with_data, active_bets, wallets, output_dir='reports')  # returns (text, picks)

    # Cleanup
    del active_bets
    del wallets
    gc.collect()

    log.info("=== Analysis complete ===")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="OracleBot (read-only)")
    parser.add_argument("command", choices=["collect", "analyze", "run", "init"],
                        help="collect=fetch data, analyze=run analysis, "
                             "run=continuous loop, init=create DB only")
    parser.add_argument("--db", default=config.DB_PATH, help="SQLite database path")
    args = parser.parse_args()

    config.DB_PATH = args.db
    conn = db.get_connection()
    db.init_db(conn)

    try:
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
                    gc.collect()
                except Exception:
                    log.exception("Cycle failed — will retry next interval")

            # Run once immediately
            cycle()

            # Schedule recurring
            schedule.every(config.SCRAPE_INTERVAL_MINUTES).minutes.do(cycle)

            while True:
                schedule.run_pending()
                time.sleep(30)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
