"""Backtest analyst Q7: sample size diagnosis. Read-only."""
import sqlite3
import sys
sys.path.insert(0, 'D:/Developer/Personal/Bots/PolyMarketTracker')

from config import BACKTEST_CUTOFF_FRACTION, S1_MIN_RESOLVED_BETS

conn = sqlite3.connect("D:/Developer/Personal/Bots/PolyMarketTracker/polymarket.db", timeout=30)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print(f"BACKTEST_CUTOFF_FRACTION = {BACKTEST_CUTOFF_FRACTION}")
print(f"S1_MIN_RESOLVED_BETS = {S1_MIN_RESOLVED_BETS}")

for min_bets in [1, 3, 5, 10, 20]:
    cur.execute("""
        SELECT m.id, COUNT(b.id) as bc
        FROM markets m
        INNER JOIN bets b ON b.market_id = m.id
        WHERE m.resolved=1
        GROUP BY m.id
        HAVING bc >= ?
    """, (min_bets,))
    rows = cur.fetchall()
    print(f"Resolved markets with >= {min_bets} bets: {len(rows)}")

cur.execute("""
    SELECT m.outcome, COUNT(DISTINCT m.id) as cnt
    FROM markets m
    INNER JOIN bets b ON b.market_id = m.id
    WHERE m.resolved=1
    GROUP BY m.outcome
""")
print("\nOutcome distribution for resolved markets that have any bets:")
for r in cur.fetchall():
    print(f"  {r['outcome']}: {r['cnt']} markets")

cur.execute("""
    SELECT COUNT(*) as cnt FROM (
        SELECT m.id
        FROM markets m
        INNER JOIN bets b ON b.market_id = m.id
        WHERE m.resolved=1
        GROUP BY m.id
        HAVING COUNT(DISTINCT b.side) >= 2
    )
""")
print(f"\nResolved markets with bets on both sides: {cur.fetchone()['cnt']}")

conn.close()
