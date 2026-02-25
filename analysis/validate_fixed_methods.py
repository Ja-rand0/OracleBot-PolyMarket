"""
Post-change validation script for the 6 recently fixed detection methods.
Run as: python analysis/validate_fixed_methods.py
"""
import sys
sys.path.insert(0, r'D:\Developer\Personal\Bots\PolyMarketTracker')
import sqlite3
from data.models import Market, Bet, Wallet
from datetime import datetime, timezone

DB_PATH = r'D:\Developer\Personal\Bots\PolyMarketTracker\data.db'

conn = sqlite3.connect(DB_PATH, timeout=30)
conn.row_factory = sqlite3.Row

# Top 3 markets by bet count
top = conn.execute(
    "SELECT market_id, COUNT(*) as cnt FROM bets GROUP BY market_id ORDER BY cnt DESC LIMIT 3"
).fetchall()
print(f"Top 3 markets: {[(r['market_id'], r['cnt']) for r in top]}")

markets_data = []
for row in top:
    mid = row['market_id']
    mrow = conn.execute("SELECT * FROM markets WHERE id=?", (mid,)).fetchone()
    if not mrow:
        print(f"  Market {mid} not in markets table, skipping")
        continue
    market = Market(
        id=mrow['id'], title=mrow['title'] or '', description=mrow['description'] or '',
        end_date=datetime.fromisoformat(mrow['end_date']) if mrow['end_date'] else datetime.now(timezone.utc).replace(tzinfo=None),
        resolved=bool(mrow['resolved']), outcome=mrow['outcome'],
        created_at=datetime.fromisoformat(mrow['created_at'])
    )
    brows = conn.execute("SELECT * FROM bets WHERE market_id=? LIMIT 500", (mid,)).fetchall()
    bets = [Bet(id=r['id'], market_id=r['market_id'], wallet=r['wallet'], side=r['side'],
                amount=r['amount'], odds=r['odds'],
                timestamp=datetime.fromisoformat(r['timestamp'])) for r in brows]
    addrs = list({b.wallet for b in bets})
    ph = ','.join('?' * len(addrs))
    wrows = conn.execute(f"SELECT * FROM wallets WHERE address IN ({ph})", addrs).fetchall()
    wallets = {r['address']: Wallet(
        address=r['address'],
        first_seen=datetime.fromisoformat(r['first_seen']) if r['first_seen'] else datetime.now(timezone.utc).replace(tzinfo=None),
        total_bets=r['total_bets'], total_volume=r['total_volume'],
        win_rate=r['win_rate'], rationality_score=r['rationality_score'],
        flagged_suspicious=bool(r['flagged_suspicious']), flagged_sandpit=bool(r['flagged_sandpit'])
    ) for r in wrows}
    markets_data.append((market, bets, wallets))
    print(f"  Loaded market {mid}: {len(bets)} bets, {len(wallets)} wallets")

conn.close()

from methods import METHODS

target_methods = ['D7', 'D8', 'T18', 'P20', 'P22', 'E10']

print("\n" + "=" * 80)
print("METHOD VALIDATION RESULTS")
print("=" * 80)

for method_id in target_methods:
    fn, category, desc = METHODS[method_id]
    print(f"\n--- {method_id}: {desc} ---")
    for market, bets, wallets in markets_data:
        try:
            result = fn(market, bets, wallets)
            print(f"  Market {market.id[:22]}...: signal={result.signal:.4f}, "
                  f"confidence={result.confidence:.4f}, "
                  f"meta_keys={list(result.metadata.keys()) if result.metadata else []}")

            if method_id == 'T18':
                is_susp = result.metadata.get('is_suspicious')
                sig_verdict = 'NON-ZERO (correct)' if result.signal != 0.0 else 'ZERO -- REGRESSION!'
                print(f"    T18 is_suspicious={is_susp}, signal verdict: {sig_verdict}")
                print(f"    T18 p_value={result.metadata.get('p_value')}, "
                      f"yes_vol={result.metadata.get('yes_volume')}, "
                      f"no_vol={result.metadata.get('no_volume')}")

            if method_id == 'P22':
                herding = result.metadata.get('herding_detected')
                indep = result.metadata.get('independence_score')
                conf_verdict = ('0.0 when no herding -- correct' if not herding and result.confidence == 0.0
                                else 'non-zero when herding -- correct' if herding and result.confidence > 0.0
                                else 'CHECK THIS')
                print(f"    P22 herding_detected={herding}, independence_score={indep}, conf_verdict={conf_verdict}")

            if method_id == 'D8':
                yes_ratio = result.metadata.get('yes_ratio', 'N/A')
                conf_verdict = 'DYNAMIC (fix applied)' if result.confidence != 0.2 else 'STATIC 0.2 -- BUG STILL PRESENT!'
                print(f"    D8 yes_ratio={yes_ratio}, {conf_verdict}")

            if method_id == 'P20':
                print(f"    P20 vwap={result.metadata.get('vwap')}, "
                      f"recent_avg={result.metadata.get('recent_avg')}, "
                      f"deviation={result.metadata.get('deviation')}")

            if method_id == 'D7':
                print(f"    D7 sharp_count={result.metadata.get('sharp_count')}, "
                      f"max_plausible={result.metadata.get('max_plausible')}, "
                      f"noise_ratio={result.metadata.get('noise_ratio')}")

            if method_id == 'E10':
                print(f"    E10 loyal_wallets={result.metadata.get('loyal_wallets')}, "
                      f"filtered_count={result.metadata.get('filtered_count')}")

        except Exception as e:
            import traceback
            print(f"  Market {market.id[:22]}...: EXCEPTION: {type(e).__name__}: {e}")
            traceback.print_exc()

print("\n" + "=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)
