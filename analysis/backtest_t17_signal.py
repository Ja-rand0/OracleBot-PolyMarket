"""Investigate T17 signal direction on the 25 backtest markets. Read-only."""
import sqlite3, json, sys, math
from datetime import datetime, timedelta
from statistics import median

sys.path.insert(0, 'D:/Developer/Personal/Bots/PolyMarketTracker')
from config import (BACKTEST_CUTOFF_FRACTION, T17_RATIONALITY_CUTOFF,
                    T17_AMOUNT_NORMALIZER, T17_UPDATE_STEP)

conn = sqlite3.connect("D:/Developer/Personal/Bots/PolyMarketTracker/polymarket.db", timeout=30)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def parse_dt(s):
    if s is None:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except:
            pass
    return None

# Get the 25 eligible markets
cur.execute("""
    SELECT m.id, m.outcome, m.created_at, m.end_date
    FROM markets m
    INNER JOIN bets b ON b.market_id = m.id
    WHERE m.resolved=1 AND m.outcome IS NOT NULL
      AND m.end_date IS NOT NULL AND m.created_at IS NOT NULL
    GROUP BY m.id
    HAVING COUNT(b.id) >= 5
""")
markets = cur.fetchall()

prior = 0.5
correct_t17 = 0
total_tested = 0
results_detail = []

for mkt in markets:
    created = parse_dt(mkt['created_at'])
    end = parse_dt(mkt['end_date'])
    if not created or not end:
        continue
    lifespan = (end - created).total_seconds()
    if lifespan <= 0:
        continue
    cutoff = created + timedelta(seconds=lifespan * BACKTEST_CUTOFF_FRACTION)

    cur.execute("""
        SELECT b.side, b.amount, b.odds, b.timestamp, b.wallet
        FROM bets b
        WHERE b.market_id = ?
        ORDER BY b.timestamp
    """, (mkt['id'],))
    all_bets = cur.fetchall()

    visible = [b for b in all_bets if parse_dt(b['timestamp']) and parse_dt(b['timestamp']) <= cutoff]
    if len(visible) < 3:
        continue

    # Get wallet rationality scores for visible wallets
    wallet_addrs = list({b['wallet'] for b in visible})
    if wallet_addrs:
        placeholders = ','.join('?' for _ in wallet_addrs)
        cur.execute(f"""
            SELECT address, rationality_score FROM wallets WHERE address IN ({placeholders})
        """, wallet_addrs)
        wallet_rat = {r['address']: r['rationality_score'] for r in cur.fetchall()}
    else:
        wallet_rat = {}

    # Compute T17
    public_log = math.log(prior / (1 - prior))
    for b in visible:
        wt = b['amount'] / T17_AMOUNT_NORMALIZER
        if b['side'] == 'YES':
            public_log += wt * T17_UPDATE_STEP
        else:
            public_log -= wt * T17_UPDATE_STEP
    public_log = max(-500.0, min(500.0, public_log))
    public_post = 1 / (1 + math.exp(-public_log))

    smart_log = math.log(prior / (1 - prior))
    smart_count = 0
    for b in visible:
        rat = wallet_rat.get(b['wallet'], 0.5)
        if rat < T17_RATIONALITY_CUTOFF:
            continue
        smart_count += 1
        wt = b['amount'] / T17_AMOUNT_NORMALIZER * rat
        if b['side'] == 'YES':
            smart_log += wt * T17_UPDATE_STEP
        else:
            smart_log -= wt * T17_UPDATE_STEP
    smart_log = max(-500.0, min(500.0, smart_log))
    smart_post = 1 / (1 + math.exp(-smart_log))

    divergence = smart_post - public_post
    signal = max(-1.0, min(1.0, divergence * 5))
    confidence = min(1.0, abs(divergence) * 3 + 0.1)

    predicted = "YES" if signal > 0 else "NO"
    correct = predicted == mkt['outcome']
    if correct:
        correct_t17 += 1
    total_tested += 1

    results_detail.append({
        'id': mkt['id'][:22],
        'outcome': mkt['outcome'],
        'predicted': predicted,
        'correct': correct,
        'signal': signal,
        'confidence': confidence,
        'public_post': public_post,
        'smart_post': smart_post,
        'divergence': divergence,
        'smart_count': smart_count,
        'visible': len(visible),
    })

print(f"T17 standalone accuracy: {correct_t17}/{total_tested} = {100*correct_t17/max(1,total_tested):.1f}%")
print(f"\nDetail (sorted by signal):")
print(f"{'Market':<24} {'Outcome':<8} {'Pred':<6} {'OK':<4} {'Signal':>8} {'Conf':>6} {'PubPost':>8} {'SmPost':>8} {'Diverg':>8} {'SmCnt':>6} {'Vis':>5}")
for r in sorted(results_detail, key=lambda x: x['signal']):
    ok = 'YES' if r['correct'] else 'NO'
    print(f"  {r['id']:<24} {r['outcome']:<8} {r['predicted']:<6} {ok:<4} {r['signal']:>8.4f} {r['confidence']:>6.3f} {r['public_post']:>8.4f} {r['smart_post']:>8.4f} {r['divergence']:>8.4f} {r['smart_count']:>6} {r['visible']:>5}")

# Check: how many markets have signal=0 (no smart bets)?
zero_signal = [r for r in results_detail if r['signal'] == 0 or (r['signal'] > -0.01 and r['signal'] < 0.01)]
print(f"\nMarkets with near-zero T17 signal: {len(zero_signal)}")
neg_signal = [r for r in results_detail if r['signal'] < 0]
pos_signal = [r for r in results_detail if r['signal'] > 0]
print(f"Markets with positive signal (YES): {len(pos_signal)}")
print(f"Markets with negative signal (NO): {len(neg_signal)}")

conn.close()
