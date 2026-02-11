"""Visual terminal dashboard for the Polymarket bot."""
from __future__ import annotations

import gc
import logging
import sys
import time
from datetime import datetime, timedelta

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
from engine.combinator import run_full_optimization
from engine.report import generate_report

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
console = Console()
log = logging.getLogger("dashboard")

MAX_ACTIVE_TRADE_FETCHES = 500
MAX_RESOLVED_TRADE_FETCHES = 100
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
        for m in markets:
            db.upsert_market(conn, m)
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
                pass
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
        for m in resolved:
            db.upsert_market(conn, m)
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
                pass
            progress.advance(task)

    console.print()
    return stats


# ---------------------------------------------------------------------------
# Wallet stats (batched)
# ---------------------------------------------------------------------------
def update_wallet_stats(conn) -> dict[str, Wallet]:
    cur = conn.cursor()
    cur.execute("""
        SELECT
            b.wallet,
            MIN(b.timestamp) AS first_seen,
            COUNT(*) AS total_bets,
            SUM(b.amount) AS total_volume,
            SUM(CASE WHEN m.outcome IS NOT NULL AND b.side = m.outcome
                THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN m.outcome IS NOT NULL
                THEN 1 ELSE 0 END) AS resolved_bets,
            SUM(CASE WHEN b.amount >= 50
                AND CAST(b.amount AS INTEGER) % 50 = 0
                THEN 1 ELSE 0 END) AS round_bets
        FROM bets b
        LEFT JOIN markets m ON b.market_id = m.id AND m.resolved = 1
        GROUP BY b.wallet
    """)

    wallets: dict[str, Wallet] = {}
    bulk = []
    for row in cur.fetchall():
        addr = row[0]
        total_bets = row[2]
        total_volume = row[3] or 0.0
        wins = row[4] or 0
        resolved_bets = row[5] or 0
        round_bets = row[6] or 0

        win_rate = wins / resolved_bets if resolved_bets > 0 else 0.0
        rr = round_bets / total_bets if total_bets > 0 else 0.0
        rationality = max(0.0, min(1.0, win_rate * 0.5 + (1 - rr) * 0.3 + 0.2))

        try:
            fs = datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            fs = datetime.now()

        w = Wallet(
            address=addr, first_seen=fs, total_bets=total_bets,
            total_volume=total_volume, win_rate=win_rate,
            rationality_score=rationality,
        )
        wallets[addr] = w
        bulk.append((
            w.address, fs.strftime("%Y-%m-%dT%H:%M:%SZ"),
            w.total_bets, w.total_volume,
            w.win_rate, w.rationality_score,
            w.flagged_suspicious, w.flagged_sandpit,
        ))

    conn.executemany(
        """INSERT INTO wallets
               (address, first_seen, total_bets, total_volume,
                win_rate, rationality_score, flagged_suspicious, flagged_sandpit)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(address) DO UPDATE SET
               total_bets=excluded.total_bets,
               total_volume=excluded.total_volume,
               win_rate=excluded.win_rate,
               rationality_score=excluded.rationality_score,
               flagged_suspicious=excluded.flagged_suspicious,
               flagged_sandpit=excluded.flagged_sandpit""",
        bulk,
    )
    conn.commit()
    return wallets


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

    # Optimization
    if len(usable) >= 10:
        with console.status(
            f"  [green]Optimizing on {len(usable)} resolved markets...[/]"
        ):
            run_full_optimization(conn, usable, resolved_bets, wallets)
        top = db.get_top_combos(conn, limit=1)
        if top:
            console.print(
                f"  [dim]Best combo     :[/] "
                f"[bold green]{top[0].combo_id}[/]  "
                f"fitness=[bold]{top[0].fitness_score:.4f}[/]"
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
            bot_prob = 0.5 + signal * 0.5
            edge = abs(bot_prob - price) * confidence
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
            pick_table.add_row("Bot says", f"{bot_prob:.0%} YES  vs  market {price:.0%}")
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
                bot_prob = 0.5 + signal * 0.5
                edge = abs(bot_prob - price) * confidence
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
        "[bold cyan]PBCareTaker[/] [dim]— Polymarket Bot Dashboard[/]",
        style="bold cyan",
        expand=True,
    ))

    cycle = 1
    try:
        while True:
            print_header(cycle)
            try:
                collect_data(conn)
                _report, picks = run_analysis(conn)
                display_report(conn, picks)
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
