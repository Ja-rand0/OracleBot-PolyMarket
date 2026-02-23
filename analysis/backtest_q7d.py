"""Backtest analyst Q7d: investigate WHY accuracy=1.0. Simulate the backtest logic. Read-only."""
import sqlite3, json, sys
from datetime import datetime, timedelta
from statistics import median

sys.path.insert(0, 'D:/Developer/Personal/Bots/PolyMarketTracker')
from config import BACKTEST_CUTOFF_FRACTION

conn = sqlite3.connect("D:/Developer/Personal/Bots/PolyMarketTracker/polymarket.db", timeout=30)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get all resolved markets with >=5 bets and valid dates
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
markets = cur.fetchall()
print(f"Markets eligible for backtest: {len(markets)}")

def parse_dt(s):
    if s is None:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

# For each market, get bets and check what survives the cutoff filter
actual_backtest_markets = []
skipped = []

for mkt in markets:
    created = parse_dt(mkt['created_at'])
    end = parse_dt(mkt['end_date'])
    if not created or not end:
        skipped.append((mkt['id'][:20], "no dates"))
        continue
    lifespan = (end - created).total_seconds()
    if lifespan <= 0:
        skipped.append((mkt['id'][:20], f"lifespan={lifespan}"))
        continue
    cutoff = created + timedelta(seconds=lifespan * BACKTEST_CUTOFF_FRACTION)

    # Get bets for this market
    cur.execute("""
        SELECT side, amount, odds, timestamp
        FROM bets
        WHERE market_id = ?
        ORDER BY timestamp
    """, (mkt['id'],))
    bets = cur.fetchall()

    visible = [b for b in bets if parse_dt(b['timestamp']) and parse_dt(b['timestamp']) <= cutoff]
    if len(visible) < 3:
        skipped.append((mkt['id'][:20], f"visible_bets={len(visible)}<3"))
        continue

    # Market odds (median YES prob)
    yes_probs = [b['odds'] for b in visible]
    market_odds = median(yes_probs) if yes_probs else 0.5
    market_implied = "YES" if market_odds > 0.5 else "NO"

    actual_backtest_markets.append({
        'id': mkt['id'][:20],
        'outcome': mkt['outcome'],
        'total_bets': mkt['total_bets'],
        'visible_bets': len(visible),
        'market_odds': market_odds,
        'market_implied': market_implied,
        'lifespan_days': lifespan / 86400,
    })

print(f"Markets that pass all backtest filters: {len(actual_backtest_markets)}")
print(f"Markets skipped: {len(skipped)}")
if skipped:
    for s in skipped[:10]:
        print(f"  skipped: {s}")

# Distribution of market_implied vs actual outcome
correct_mkt = sum(1 for m in actual_backtest_markets if m['market_implied'] == m['outcome'])
print(f"\nMarket-implied baseline accuracy: {correct_mkt}/{len(actual_backtest_markets)} = {100*correct_mkt/max(1,len(actual_backtest_markets)):.1f}%")

# Are markets where the bot adds edge (market_implied != outcome)?
wrong_mkt = [m for m in actual_backtest_markets if m['market_implied'] != m['outcome']]
print(f"Markets where market-implied is WRONG (where bot could add edge): {len(wrong_mkt)}")
for m in wrong_mkt:
    print(f"  {m['id']}  outcome={m['outcome']}  market_implied={m['market_implied']}  market_odds={m['market_odds']:.3f}  visible={m['visible_bets']}")

# Median YES probability across all backtest markets
all_odds = [m['market_odds'] for m in actual_backtest_markets]
print(f"\nMedian market odds (YES prob): {median(all_odds):.4f}")
print(f"Markets with market_odds > 0.5 (market implies YES): {sum(1 for o in all_odds if o > 0.5)}")
print(f"Markets with market_odds <= 0.5 (market implies NO): {sum(1 for o in all_odds if o <= 0.5)}")

print("\nAll backtest markets (sorted by market_odds):")
for m in sorted(actual_backtest_markets, key=lambda x: x['market_odds']):
    correct_flag = "OK" if m['market_implied'] == m['outcome'] else "MISS"
    print(f"  {m['id']:<22} outcome={m['outcome']:<4} implied={m['market_implied']:<4} odds={m['market_odds']:.3f}  visible={m['visible_bets']:4d}  {correct_flag}")

conn.close()
