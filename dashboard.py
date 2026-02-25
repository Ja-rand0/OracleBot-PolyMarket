"""Visual terminal dashboard for OracleBot."""
from __future__ import annotations

import gc
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

import config
from data import db
from data.models import Bet, Wallet
from data.scraper import fetch_markets, fetch_resolved_markets, fetch_trades_for_market
from engine.backtest import split_holdout
from engine.combinator import run_full_optimization
from engine.report import generate_report
from main import update_wallet_stats

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
console = Console()
log = logging.getLogger("dashboard")

MAX_ACTIVE_TRADE_FETCHES = 500
MAX_RESOLVED_TRADE_FETCHES = 100
MAX_BACKFILL_FETCHES = 200
MIN_BETS_FOR_BACKTEST = 5


def setup_logging():
    """Route all logging to bot.log — rich handles the console."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    fh = logging.FileHandler("bot.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    ))
    root.addHandler(fh)


# ---------------------------------------------------------------------------
# Progress bar factory
# ---------------------------------------------------------------------------
def _progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("  {task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[dim]|[/]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
def print_header(cycle: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    console.print()
    console.print(Panel(
        f"[bold cyan]POLYMARKET BOT[/]  [dim]|[/]  "
        f"Cycle [bold]#{cycle}[/]  [dim]|[/]  {now}",
        style="cyan",
        expand=True,
    ))


# ---------------------------------------------------------------------------
# Data Collection
# ---------------------------------------------------------------------------
def collect_data(conn) -> dict:
    stats = {"markets": 0, "trades": 0, "trade_markets": 0, "resolved": 0}
    console.print("\n  [bold yellow]DATA COLLECTION[/]\n")

    # --- Active markets ---
    with console.status("  [green]Fetching active markets...[/]"):
        markets = fetch_markets(active_only=True)
    log.info("Upserting %d active markets to DB...", len(markets))
    for m in markets:
        db.upsert_market(conn, m)
    conn.commit()
    log.info("Active market upserts complete")
    stats["markets"] = len(markets)
    console.print(f"  [dim]Markets stored :[/] [bold]{len(markets):,}[/]")

    # --- Trades for active markets ---
    total_trades = 0
    trade_markets = 0
    cap = min(len(markets), MAX_ACTIVE_TRADE_FETCHES)

    with _progress() as progress:
        task = progress.add_task("[cyan]Active trades", total=cap)
        for i, m in enumerate(markets):
            if i >= cap:
                break
            try:
                since = db.get_latest_bet_timestamp(conn, m.id)
                trades = fetch_trades_for_market(m.id, since=since)
                if trades:
                    db.insert_bets_bulk(conn, trades)
                    total_trades += len(trades)
                    trade_markets += 1
            except Exception:
                log.exception("Failed to fetch trades for market %s", m.id[:16])
            progress.advance(task)

    stats["trades"] = total_trades
    stats["trade_markets"] = trade_markets
    console.print(
        f"  [dim]New trades    :[/] [bold]{total_trades:,}[/]  "
        f"from {trade_markets} markets"
    )

    # --- Resolved markets ---
    with console.status("  [green]Fetching resolved markets...[/]"):
        resolved = fetch_resolved_markets(max_pages=3)
    log.info("Upserting %d resolved markets to DB...", len(resolved))
    for m in resolved:
        db.upsert_market(conn, m)
    conn.commit()
    log.info("Resolved market upserts complete")
    stats["resolved"] = len(resolved)
    console.print(f"  [dim]Resolved       :[/] [bold]{len(resolved):,}[/]")

    # --- Trades for resolved markets ---
    cap_r = min(len(resolved), MAX_RESOLVED_TRADE_FETCHES)
    with _progress() as progress:
        task = progress.add_task("[cyan]Resolved trades", total=cap_r)
        for i, m in enumerate(resolved):
            if i >= cap_r:
                break
            try:
                since = db.get_latest_bet_timestamp(conn, m.id)
                trades = fetch_trades_for_market(m.id, since=since)
                if trades:
                    db.insert_bets_bulk(conn, trades)
            except Exception:
                log.exception("Failed to fetch trades for resolved market %s", m.id[:16])
            progress.advance(task)

    # --- Backfill: resolved markets already in DB with no/few bets ---
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
    with _progress() as progress:
        task = progress.add_task("[magenta]Backfill trades", total=len(backfill_markets))
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
            progress.advance(task)
    log.info(
        "Backfill complete: %d trades added | %d/%d markets had data | %d/%d returned empty",
        backfill_added,
        backfill_with_data, len(backfill_markets),
        backfill_empty, len(backfill_markets),
    )
    console.print(
        f"  [dim]Backfilled     :[/] [bold]{backfill_added:,}[/]  trades  "
        f"[dim]({backfill_with_data} with data / {backfill_empty} empty)[/]"
    )

    console.print()
    return stats


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def run_analysis(conn) -> tuple[str | None, list]:
    """Run analysis pipeline. Returns (report_text, scored_markets)."""
    console.print("  [bold yellow]ANALYSIS[/]\n")

    # Wallet stats
    with console.status("  [green]Computing wallet profiles...[/]"):
        wallets = update_wallet_stats(conn)
    console.print(f"  [dim]Wallets        :[/] [bold]{len(wallets):,}[/]")

    # Resolved markets
    resolved_markets = db.get_all_markets(conn, resolved_only=True)
    resolved_bets: dict[str, list[Bet]] = {}
    for m in resolved_markets:
        bets = db.get_bets_for_market(conn, m.id)
        if len(bets) >= MIN_BETS_FOR_BACKTEST:
            resolved_bets[m.id] = bets
    usable = [m for m in resolved_markets if m.id in resolved_bets]
    console.print(f"  [dim]Backtestable   :[/] [bold]{len(usable)}[/]")

    # Holdout split
    train_markets, holdout_markets = split_holdout(usable, config.HOLDOUT_FRACTION)
    train_bets = {m.id: resolved_bets[m.id] for m in train_markets if m.id in resolved_bets}
    holdout_bets_map = {m.id: resolved_bets[m.id] for m in holdout_markets if m.id in resolved_bets}
    console.print(
        f"  [dim]Holdout split  :[/] [bold]{len(train_markets)}[/] train / "
        f"[bold]{len(holdout_markets)}[/] holdout (temporal)"
    )

    if len(holdout_markets) < 5:
        holdout_markets, holdout_bets_map = None, None

    # Optimization
    if len(usable) >= 10:
        with console.status(
            f"  [green]Optimizing on {len(train_markets)} train markets...[/]"
        ):
            run_full_optimization(conn, train_markets, train_bets, wallets,
                                  holdout_markets, holdout_bets_map)
        top = db.get_top_combos(conn, limit=1)
        if top:
            console.print(
                f"  [dim]Best combo     :[/] "
                f"[bold green]{top[0].combo_id}[/]  "
                f"fitness=[bold]{top[0].fitness_score:.4f}[/]"
            )
        holdout_rows = db.get_latest_holdout_results(conn, limit=1)
        if holdout_rows:
            row = holdout_rows[0]
            gap = row[4] - row[3]  # holdout_fitness - train_fitness
            gap_color = "red" if gap < -0.05 else "green"
            console.print(
                f"  [dim]Holdout valid  :[/] "
                f"train=[bold]{row[3]:.4f}[/] holdout=[bold]{row[4]:.4f}[/] "
                f"gap=[bold {gap_color}]{gap:+.4f}[/]  "
                f"[dim]({row[1]} train / {row[2]} holdout markets)[/]"
            )
    else:
        console.print(
            f"  [dim]Skipping optimization (need 10+, have {len(usable)})[/]"
        )

    del resolved_bets, resolved_markets
    gc.collect()

    # Report
    active_markets = [
        m for m in db.get_all_markets(conn) if not m.resolved
    ]
    active_bets: dict[str, list[Bet]] = {}
    for m in active_markets[:200]:
        bets = db.get_bets_for_market(conn, m.id)
        if len(bets) >= MIN_BETS_FOR_BACKTEST:
            active_bets[m.id] = bets
    active_with_data = [m for m in active_markets if m.id in active_bets]

    report = None
    picks = []
    with console.status("  [green]Generating report...[/]"):
        report, picks = generate_report(conn, active_with_data, active_bets, wallets, output_dir='reports')

    from engine.relationships import persist_graph_relationships
    persist_graph_relationships(conn, active_with_data, active_bets, wallets)

    del active_bets, wallets
    gc.collect()

    console.print()
    return report, picks


# ---------------------------------------------------------------------------
# Display tables
# ---------------------------------------------------------------------------
def display_report(conn, picks: list | None = None):
    console.print("  [bold yellow]REPORT[/]\n")

    # --- TOP 3 PICKS ---
    # picks already filtered and ranked by edge over market by report.py
    if picks:
        top3 = picks[:3]
        if not top3:
            console.print("  [dim]No edge picks yet — need more data.[/]\n")
        for i, entry in enumerate(top3):
            market, ratio, signal, confidence, n_bets = entry[:5]
            price = entry[5] if len(entry) > 5 else 0.5
            side = "YES" if signal > 0 else "NO"
            buy_price = price if signal > 0 else (1 - price)
            directional_score = 0.5 + signal * 0.5
            edge = abs(directional_score - price) * confidence
            side_style = "bold green" if signal > 0 else "bold red"
            border = "green" if signal > 0 else "red"

            pick_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
            pick_table.add_column(style="dim", min_width=16)
            pick_table.add_column(style="bold white", min_width=30)
            pick_table.add_row("Action", f"[{side_style}]BET {side}[/]")
            pick_table.add_row("Market", market.title[:70])
            pick_table.add_row("YES price", f"${price:.2f}")
            pick_table.add_row("NO price", f"${1-price:.2f}")
            pick_table.add_row("You buy at", f"[bold]${buy_price:.2f}[/]  →  pays [bold]$1.00[/] if correct")
            pick_table.add_row("Score", f"{directional_score:.0%} YES  vs  market {price:.0%}")
            pick_table.add_row("Edge", f"[bold yellow]{edge:.2f}[/]")
            pick_table.add_row("Confidence", f"{confidence:.2f}")
            pick_table.add_row("Madness", f"{ratio:.2f}")
            pick_table.add_row("Bets analyzed", str(n_bets))
            if market.description:
                desc = market.description[:120].replace("\n", " ")
                pick_table.add_row("Details", f"[dim]{desc}[/]")

            console.print(Panel(
                pick_table,
                title=f"[bold yellow]PICK #{i+1}[/]  [{side_style}]BET {side}[/]",
                border_style=border,
                expand=False,
            ))

        # --- Rest of exploitable markets ---
        rest = picks[3:20]
        if rest:
            rt = Table(box=box.SIMPLE, show_lines=False)
            rt.add_column("#", style="dim", justify="right", width=3)
            rt.add_column("Market", style="white", min_width=30)
            rt.add_column("Action", justify="center", min_width=8)
            rt.add_column("Buy At", justify="right")
            rt.add_column("Edge", justify="right", style="yellow")
            rt.add_column("Conf", justify="right")
            rt.add_column("Madness", justify="right", style="dim")
            for i, entry in enumerate(rest, start=4):
                market, ratio, signal, confidence, n_bets = entry[:5]
                price = entry[5] if len(entry) > 5 else 0.5
                side = "YES" if signal > 0 else "NO" if signal < 0 else "—"
                buy_price = price if signal > 0 else (1 - price) if signal < 0 else 0
                directional_score = 0.5 + signal * 0.5
                edge = abs(directional_score - price) * confidence
                side_style = "green" if signal > 0 else "red"
                rt.add_row(
                    str(i),
                    market.title[:50],
                    f"[{side_style}]BET {side}[/]",
                    f"${buy_price:.2f}",
                    f"{edge:.2f}",
                    f"{confidence:.2f}",
                    f"{ratio:.2f}",
                )
            console.print(Panel(
                rt,
                title="[bold]Other Opportunities[/]",
                border_style="dim",
                expand=False,
            ))

    # --- Database stats ---
    cur = conn.cursor()
    mc = cur.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
    rc = cur.execute("SELECT COUNT(*) FROM markets WHERE resolved=1").fetchone()[0]
    bc = cur.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
    wc = cur.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]

    st = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    st.add_column(style="dim")
    st.add_column(justify="right", style="bold white")
    st.add_row("Markets", f"{mc:,}")
    st.add_row("Resolved", f"{rc:,}")
    st.add_row("Trades", f"{bc:,}")
    st.add_row("Wallets", f"{wc:,}")
    console.print(Panel(st, title="[bold]Database[/]", border_style="dim", expand=False))

    # --- Top combos ---
    top = db.get_top_combos(conn, limit=5)
    if top:
        ct = Table(box=box.ROUNDED, show_lines=False)
        ct.add_column("Combo", style="cyan", min_width=20)
        ct.add_column("Accuracy", justify="right", style="green")
        ct.add_column("Edge", justify="right")
        ct.add_column("FPR", justify="right", style="red")
        ct.add_column("Fitness", justify="right", style="bold yellow")
        for cr in top:
            ct.add_row(
                cr.combo_id,
                f"{cr.accuracy:.1%}",
                f"{cr.edge_vs_market:+.3f}",
                f"{cr.false_positive_rate:.1%}",
                f"{cr.fitness_score:.4f}",
            )
        console.print(Panel(ct, title="[bold]Top Combos[/]", border_style="dim", expand=False))

    # --- Suspicious wallets ---
    sus = conn.execute(
        "SELECT address, win_rate, total_bets, total_volume "
        "FROM wallets WHERE flagged_suspicious=1 AND total_bets>=10 "
        "ORDER BY win_rate DESC LIMIT 10"
    ).fetchall()
    if sus:
        wt = Table(box=box.SIMPLE, show_lines=False)
        wt.add_column("Wallet", style="dim")
        wt.add_column("Win Rate", justify="right", style="green")
        wt.add_column("Bets", justify="right")
        wt.add_column("Volume", justify="right", style="cyan")
        for r in sus:
            wt.add_row(
                r[0][:14] + "...",
                f"{r[1]:.0%}",
                str(r[2]),
                f"${r[3]:,.0f}",
            )
        console.print(Panel(wt, title="[bold]Suspicious Wallets[/]", border_style="dim", expand=False))

    console.print()


# ---------------------------------------------------------------------------
# Countdown between cycles
# ---------------------------------------------------------------------------
def countdown(minutes: int):
    end = datetime.now() + timedelta(minutes=minutes)
    try:
        with console.status("") as status:
            while datetime.now() < end:
                left = end - datetime.now()
                m, s = divmod(int(left.total_seconds()), 60)
                status.update(f"  [dim]Next cycle in[/] [bold]{m:02d}:{s:02d}[/]")
                time.sleep(1)
    except KeyboardInterrupt:
        console.print()
        raise


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run():
    setup_logging()

    conn = db.get_connection()
    db.init_db(conn)

    console.print(Panel(
        "[bold cyan]OracleBot[/] [dim]— Dashboard[/]",
        style="bold cyan",
        expand=True,
    ))

    cycle = 1
    last_analyzed: datetime | None = None
    try:
        while True:
            print_header(cycle)
            try:
                collect_data(conn)

                # Analyze on first cycle, then every ANALYZE_INTERVAL_HOURS
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                due = last_analyzed is None or (
                    now - last_analyzed >= timedelta(hours=config.ANALYZE_INTERVAL_HOURS)
                )
                if due:
                    _report, picks = run_analysis(conn)
                    last_analyzed = datetime.now(timezone.utc).replace(tzinfo=None)
                    display_report(conn, picks)
                else:
                    next_analyze = last_analyzed + timedelta(hours=config.ANALYZE_INTERVAL_HOURS)
                    console.print(f"  [dim]Next analysis in "
                                  f"{(next_analyze - now).seconds // 60} min — collecting only[/]")

                gc.collect()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                console.print(f"\n  [bold red]Cycle failed:[/] {e}")
                console.print("  [dim]Will retry next interval — see bot.log[/]")
                log.exception("Cycle %d failed", cycle)

            console.rule("[dim]cycle complete[/]")
            countdown(config.SCRAPE_INTERVAL_MINUTES)
            cycle += 1
    except KeyboardInterrupt:
        console.print("\n  [bold yellow]Stopped by user (Ctrl+C)[/]\n")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
