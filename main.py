"""Entry point — data collection loop, analysis, and reporting."""
from __future__ import annotations

import argparse
import gc
import logging
import time
from datetime import datetime, timedelta, timezone

import schedule

import config
from data import db
from data.models import Bet, Wallet
from data.scraper import fetch_markets, fetch_resolved_markets, fetch_trades_for_market, fetch_leaderboard
from engine.backtest import split_holdout
from engine.combinator import run_full_optimization
from engine.report import generate_report

log = logging.getLogger("main")

# Max active markets to fetch trades for per cycle (avoid hammering API)
MAX_ACTIVE_TRADE_FETCHES = 500
# Max resolved markets to fetch trades for per cycle (bumped to build backtest set faster)
MAX_RESOLVED_TRADE_FETCHES = 500
# Max resolved markets to backfill from DB per cycle (drains the empty-bet backlog)
MAX_BACKFILL_FETCHES = 200
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
            SUM(CASE WHEN b.amount >= 50 AND CAST(b.amount AS INTEGER) % 50 = 0 THEN 1 ELSE 0 END) AS round_bets,
            SUM(CASE WHEN b.side = 'YES' THEN 1 ELSE 0 END) AS yes_bets
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
        yes_bets = row[7] or 0

        win_rate = wins / resolved_bets if resolved_bets > 0 else 0.0
        round_ratio = round_bets / total_bets if total_bets > 0 else 0.0
        yes_bet_ratio = yes_bets / total_bets if total_bets > 0 else 0.5
        # Rationality score: provisional heuristic combining two behavioural signals.
        # Weights (0.5 / 0.3) are engineering estimates, not empirically validated.
        #   win_rate * 0.5      — track record; winning bets suggest informed decisions
        #   (1-round_ratio)*0.3 — precision proxy; non-round amounts suggest deliberate sizing
        # Max possible score: 0.8 (not 1.0) — acknowledges that no wallet is "perfectly rational".
        # To validate: correlate rationality_score against future win_rate on held-out markets.
        rationality = max(0.0, min(1.0, win_rate * 0.5 + (1 - round_ratio) * 0.3))

        try:
            fs = datetime.strptime(first_seen_str, "%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            fs = datetime.now(timezone.utc).replace(tzinfo=None)

        w = Wallet(
            address=addr,
            first_seen=fs,
            total_bets=total_bets,
            total_volume=total_volume,
            win_rate=win_rate,
            rationality_score=rationality,
            yes_bet_ratio=yes_bet_ratio,
        )
        wallets[addr] = w
        bulk_rows.append((
            w.address, fs.strftime("%Y-%m-%dT%H:%M:%SZ"),
            w.total_bets, w.total_volume,
            w.win_rate, w.rationality_score,
            w.flagged_suspicious, w.flagged_sandpit,
            w.yes_bet_ratio,
        ))

    conn.executemany(
        """
        INSERT INTO wallets (address, first_seen, total_bets, total_volume,
                             win_rate, rationality_score, flagged_suspicious, flagged_sandpit,
                             yes_bet_ratio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(address) DO UPDATE SET
            total_bets=excluded.total_bets,
            total_volume=excluded.total_volume,
            win_rate=excluded.win_rate,
            rationality_score=excluded.rationality_score,
            flagged_suspicious=excluded.flagged_suspicious,
            flagged_sandpit=excluded.flagged_sandpit,
            yes_bet_ratio=excluded.yes_bet_ratio
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

    # Seed wallet table with known sharp traders from leaderboard (INSERT OR IGNORE)
    try:
        leaderboard = fetch_leaderboard(limit=200, time_period="ALL", order_by="PNL")
        seeded = db.seed_wallets_batch(conn, leaderboard)
        log.info("Leaderboard seed: %d new wallets added (200 fetched)", seeded)
    except Exception:
        log.warning("Leaderboard seeding failed — continuing without it")

    # Fetch active markets (metadata only — cheap)
    markets = fetch_markets(active_only=True)
    for m in markets:
        db.upsert_market(conn, m)
    conn.commit()
    log.info("Stored %d active markets", len(markets))

    # Fetch trades for a capped subset of active markets — highest volume first
    markets_by_volume = sorted(markets, key=lambda m: m.volume, reverse=True)
    total_trades = 0
    markets_with_trades = 0
    fetched = 0
    for i, m in enumerate(markets_by_volume):
        if fetched >= MAX_ACTIVE_TRADE_FETCHES:
            break
        if (i + 1) % 200 == 0:
            log.info("  Trade fetch progress: %d / %d markets (fetched %d)",
                     i + 1, len(markets_by_volume), fetched)
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

    # Fetch resolved markets for backtesting (10 pages = up to 10k market metadata)
    resolved = fetch_resolved_markets(max_pages=10)
    for m in resolved:
        db.upsert_market(conn, m)
    conn.commit()
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

    # Backfill: resolved markets already in DB with no/few bets (not in current fetch window)
    backfill_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=config.BACKFILL_MAX_AGE_DAYS)
    backfill_markets = db.get_resolved_markets_needing_backfill(
        conn, min_bets=MIN_BETS_FOR_BACKTEST, limit=MAX_BACKFILL_FETCHES,
        min_end_date=backfill_cutoff,
    )
    log.info("Backfill: %d resolved markets in DB have fewer than %d bets (cutoff: %s)",
             len(backfill_markets), MIN_BETS_FOR_BACKTEST, backfill_cutoff.strftime("%Y-%m-%d"))
    backfill_added = 0
    backfill_with_data = 0
    backfill_empty = 0
    for i, m in enumerate(backfill_markets):
        log.debug("Backfill [%d/%d] %s | outcome=%s end=%s",
                  i + 1, len(backfill_markets), m.id[:16], m.outcome, m.end_date)
        try:
            trades = fetch_trades_for_market(m.id)
            if trades:
                db.insert_bets_bulk(conn, trades)
                backfill_added += len(trades)
                backfill_with_data += 1
                log.debug("Backfill [%d/%d] %s — got %d trades",
                          i + 1, len(backfill_markets), m.id[:16], len(trades))
            else:
                backfill_empty += 1
                log.debug("Backfill [%d/%d] %s — no trades returned (API dry)",
                          i + 1, len(backfill_markets), m.id[:16])
        except Exception:
            log.exception("Failed to backfill trades for resolved market %s", m.id[:16])
    log.info(
        "Backfill complete: %d trades added | %d/%d markets had data | %d/%d returned empty",
        backfill_added,
        backfill_with_data, len(backfill_markets),
        backfill_empty, len(backfill_markets),
    )

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

    # Resolve any pending predictions before generating new ones
    resolved_count = db.update_prediction_outcomes(conn)
    if resolved_count:
        log.info("Updated %d predictions with resolved outcomes", resolved_count)

    wallets = update_wallet_stats(conn)

    # Only load resolved markets that actually have bet data (via SQL count)
    resolved_markets = db.get_all_markets(conn, resolved_only=True)

    # Load bets only for resolved markets with enough data
    resolved_bets = _load_bets_for_markets(conn, resolved_markets)
    usable_resolved = [m for m in resolved_markets if m.id in resolved_bets]
    log.info("Resolved markets with %d+ bets: %d", MIN_BETS_FOR_BACKTEST, len(usable_resolved))

    train_markets, holdout_markets = split_holdout(usable_resolved, config.HOLDOUT_FRACTION)
    train_bets = {m.id: resolved_bets[m.id] for m in train_markets if m.id in resolved_bets}
    holdout_bets = {m.id: resolved_bets[m.id] for m in holdout_markets if m.id in resolved_bets}
    log.info("Holdout split: %d train / %d holdout markets (temporal, oldest→train)",
             len(train_markets), len(holdout_markets))

    if len(holdout_markets) < 5:
        log.warning("Holdout set too small (%d markets) — skipping validation", len(holdout_markets))
        holdout_markets, holdout_bets = None, None

    if len(usable_resolved) >= 10:
        log.info("Running optimization on %d train markets", len(train_markets))
        run_full_optimization(conn, train_markets, train_bets, wallets, holdout_markets, holdout_bets)
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

    from engine.relationships import persist_graph_relationships
    persist_graph_relationships(conn, active_with_data, active_bets, wallets)

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
            log.info(
                "Starting collect loop (every %d min) + analyze loop (every %d hr)",
                config.SCRAPE_INTERVAL_MINUTES,
                config.ANALYZE_INTERVAL_HOURS,
            )

            def collect_cycle():
                try:
                    collect_data(conn)
                    gc.collect()
                except Exception:
                    log.exception("Collect cycle failed — will retry next interval")

            def analyze_cycle():
                try:
                    run_analysis(conn)
                    gc.collect()
                except Exception:
                    log.exception("Analyze cycle failed")

            # Run collect immediately, defer first analyze
            collect_cycle()

            schedule.every(config.SCRAPE_INTERVAL_MINUTES).minutes.do(collect_cycle)
            schedule.every(config.ANALYZE_INTERVAL_HOURS).hours.do(analyze_cycle)

            while True:
                schedule.run_pending()
                time.sleep(30)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
