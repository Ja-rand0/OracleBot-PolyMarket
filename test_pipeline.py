"""End-to-end pipeline test: fetch data, build profiles, backtest combos."""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from data import db
from data.scraper import fetch_resolved_markets, fetch_trades_for_market
from main import update_wallet_stats
from engine.backtest import backtest_combo

conn = db.get_connection()
db.init_db(conn)

# 1. Fetch resolved markets from CLOB API
print("=" * 60)
print("STEP 1: Fetching resolved markets...")
print("=" * 60)
resolved = fetch_resolved_markets(max_pages=5)
for m in resolved:
    db.upsert_market(conn, m)
print(f"\nResolved markets found: {len(resolved)}")
for m in resolved[:5]:
    print(f"  [{m.outcome:>3}] {m.title[:65]}")

# 2. Fetch trades for resolved markets
print("\n" + "=" * 60)
print("STEP 2: Fetching trades for resolved markets...")
print("=" * 60)
has_trades = 0
for i, m in enumerate(resolved):
    if i >= 80:
        break
    trades = fetch_trades_for_market(m.id, max_pages=5)
    if trades:
        db.insert_bets_bulk(conn, trades)
        has_trades += 1
print(f"\nMarkets with trade data: {has_trades}")

# 3. Update wallet stats
print("\n" + "=" * 60)
print("STEP 3: Building wallet profiles...")
print("=" * 60)
wallets = update_wallet_stats(conn)
print(f"Wallets with computed stats: {len(wallets)}")

top_w = sorted(
    [w for w in wallets.values() if w.total_bets >= 3],
    key=lambda w: w.win_rate,
    reverse=True,
)[:5]
if top_w:
    print("\nTop wallets by win rate:")
    for w in top_w:
        print(
            f"  {w.address[:16]}... WR={w.win_rate:.0%} "
            f"bets={w.total_bets} vol=${w.total_volume:,.0f} "
            f"rationality={w.rationality_score:.2f}"
        )

# 4. Backtest
print("\n" + "=" * 60)
print("STEP 4: Backtesting method combos...")
print("=" * 60)
resolved_markets = db.get_all_markets(conn, resolved_only=True)
bets_by_market = {}
for m in resolved_markets:
    b = db.get_bets_for_market(conn, m.id)
    if b:
        bets_by_market[m.id] = b

markets_with_bets = [
    m
    for m in resolved_markets
    if m.id in bets_by_market and len(bets_by_market[m.id]) >= 5
]
print(f"Resolved markets with 5+ bets: {len(markets_with_bets)}")

if markets_with_bets:
    combos = [
        ["E15"],
        ["T19"],
        ["D5"],
        ["P21"],
        ["E14", "E15"],
        ["S2", "T19"],
        ["D5", "E15", "T19"],
        ["E14", "E15", "T17", "P21"],
    ]

    print(f"\n{'Combo':<30} {'Accuracy':>9} {'Edge':>7} {'FPR':>7} {'Fitness':>8}")
    print("-" * 70)
    for combo in combos:
        cr = backtest_combo(combo, markets_with_bets, bets_by_market, wallets)
        db.insert_method_result(conn, cr)
        print(
            f"{cr.combo_id:<30} {cr.accuracy:>8.1%} "
            f"{cr.edge_vs_market:>7.3f} {cr.false_positive_rate:>6.1%} "
            f"{cr.fitness_score:>8.4f}"
        )
else:
    print("Not enough resolved markets with trade data for backtesting.")
    print("The bot needs more data — run 'python main.py collect' a few times")
    print("or wait for markets to resolve.")

print("\n" + "=" * 60)
print("PIPELINE TEST COMPLETE")
print("=" * 60)
