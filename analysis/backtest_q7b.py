"""Backtest analyst Q7b: deeper accuracy diagnosis. Read-only."""
import sqlite3
import sys
sys.path.insert(0, 'D:/Developer/Personal/Bots/PolyMarketTracker')

conn = sqlite3.connect("D:/Developer/Personal/Bots/PolyMarketTracker/polymarket.db", timeout=30)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# How many markets pass the backtest filters?
# backtest.py requires: resolved=True, outcome not None, >=5 bets, lifespan>0, visible_bets>=3
# BACKTEST_CUTOFF_FRACTION=0.7 means visible_bets = bets placed in first 70% of market lifespan

# Approximate: markets that have >=5 bets and both end_date and created_at defined
cur.execute("""
    SELECT m.id, m.outcome, m.created_at, m.end_date,
           COUNT(b.id) as total_bets
    FROM markets m
    INNER JOIN bets b ON b.market_id = m.id
    WHERE m.resolved=1 AND m.outcome IS NOT NULL
      AND m.end_date IS NOT NULL AND m.created_at IS NOT NULL
    GROUP BY m.id
    HAVING total_bets >= 5
    ORDER BY total_bets DESC
""")
rows = cur.fetchall()
print(f"Resolved markets with >=5 bets and valid dates: {len(rows)}")

# Outcome breakdown for those markets
from collections import Counter
outcomes = Counter(r['outcome'] for r in rows)
print("Outcome breakdown:")
for outcome, cnt in sorted(outcomes.items()):
    print(f"  {outcome}: {cnt} ({100 * cnt / len(rows):.1f}%)")

total_yes = outcomes.get('YES', 0)
total_no = outcomes.get('NO', 0)
total = total_yes + total_no
if total > 0:
    print(f"\nBaseline accuracy (always-YES strategy): {100 * total_yes / total:.1f}%")
    print(f"Baseline accuracy (always-NO strategy): {100 * total_no / total:.1f}%")

# How many of those 28 markets had most bets BEFORE the cutoff?
# Check bet timing relative to market lifespan
cur.execute("""
    SELECT m.id, m.outcome, m.created_at, m.end_date,
           COUNT(b.id) as total_bets,
           MIN(b.timestamp) as first_bet,
           MAX(b.timestamp) as last_bet
    FROM markets m
    INNER JOIN bets b ON b.market_id = m.id
    WHERE m.resolved=1 AND m.outcome IS NOT NULL
      AND m.end_date IS NOT NULL AND m.created_at IS NOT NULL
    GROUP BY m.id
    HAVING total_bets >= 5
    ORDER BY total_bets DESC
""")
detail_rows = cur.fetchall()

# Check if markets with late bets might filter down to < 3 visible bets at cutoff
print("\nDetailed bet timing for resolved markets with >=5 bets:")
print(f"{'Market ID':<24} {'Outcome':<8} {'Bets':<6} {'Created':<22} {'End':<22}")
for r in detail_rows[:20]:
    print(f"  {r['id'][:22]:<24} {r['outcome']:<8} {r['total_bets']:<6} {r['created_at']:<22} {r['end_date']:<22}")

conn.close()
