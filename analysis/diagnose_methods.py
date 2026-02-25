"""
Diagnostic script for 11 underperforming detection methods.
Runs each method against the 5 markets with most bets and reports
signal, confidence, metadata, and diagnosis.
"""
import sys
sys.path.insert(0, r'D:\Developer\Personal\Bots\PolyMarketTracker')

import sqlite3
from data.models import Market, Bet, Wallet
from datetime import datetime, timezone
import traceback

DB_PATH = r'D:\Developer\Personal\Bots\PolyMarketTracker\data.db'

# ── Import all 11 methods ──────────────────────────────────────────────────────
import_results = {}
methods = {}

def try_import(fn_name, module_path, actual_fn_name=None):
    if actual_fn_name is None:
        actual_fn_name = fn_name
    try:
        mod = __import__(module_path, fromlist=[actual_fn_name])
        fn = getattr(mod, actual_fn_name)
        methods[fn_name] = fn
        import_results[fn_name] = "OK"
    except ImportError as e:
        import_results[fn_name] = f"IMPORT ERROR: {e}"
    except AttributeError as e:
        import_results[fn_name] = f"ATTR ERROR: {e}"
    except Exception as e:
        import_results[fn_name] = f"ERROR: {type(e).__name__}: {e}"

try_import("D7", "methods.discrete", "d7_pigeonhole")
try_import("D8", "methods.discrete", "d8_boolean_sat")
try_import("E10", "methods.emotional", "e10_loyalty_bias")
try_import("E13", "methods.emotional", "e13_hype_detection")
try_import("E15", "methods.emotional", "e15_round_number")   # actual name is e15_round_number
try_import("T18", "methods.statistical", "t18_benfords_law")
try_import("T19", "methods.statistical", "t19_zscore_outlier")
try_import("P20", "methods.psychological", "p20_nash_deviation")
try_import("P21", "methods.psychological", "p21_prospect_theory")
try_import("P22", "methods.psychological", "p22_herding")
try_import("M27", "methods.markov", "m27_flow_momentum")

# ── DB helpers ─────────────────────────────────────────────────────────────────
def load_data():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row

    # Top 5 markets by bet count
    top = db.execute(
        "SELECT market_id, COUNT(*) as cnt FROM bets GROUP BY market_id ORDER BY COUNT(*) DESC LIMIT 5"
    ).fetchall()

    results = []
    for row in top:
        market_id = row["market_id"]
        cnt = row["cnt"]

        mrow = db.execute("SELECT * FROM markets WHERE id = ?", (market_id,)).fetchone()
        if not mrow:
            continue

        market = Market(
            id=mrow["id"],
            title=mrow["title"],
            description=mrow["description"] or "",
            end_date=datetime.fromisoformat(mrow["end_date"]) if mrow["end_date"] else datetime.now(timezone.utc).replace(tzinfo=None),
            resolved=bool(mrow["resolved"]),
            outcome=mrow["outcome"],
            created_at=datetime.fromisoformat(mrow["created_at"]),
        )

        brows = db.execute(
            "SELECT * FROM bets WHERE market_id = ? LIMIT 500", (market_id,)
        ).fetchall()
        bets = [
            Bet(
                id=r["id"],
                market_id=r["market_id"],
                wallet=r["wallet"],
                side=r["side"],
                amount=r["amount"],
                odds=r["odds"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in brows
        ]

        wallet_addresses = list({b.wallet for b in bets})
        placeholders = ",".join("?" * len(wallet_addresses))
        wrows = db.execute(
            f"SELECT * FROM wallets WHERE address IN ({placeholders})", wallet_addresses
        ).fetchall()
        wallets = {
            r["address"]: Wallet(
                address=r["address"],
                first_seen=datetime.fromisoformat(r["first_seen"]) if r["first_seen"] else datetime.now(timezone.utc).replace(tzinfo=None),
                total_bets=r["total_bets"],
                total_volume=r["total_volume"],
                win_rate=r["win_rate"],
                rationality_score=r["rationality_score"],
                flagged_suspicious=bool(r["flagged_suspicious"]),
                flagged_sandpit=bool(r["flagged_sandpit"]),
            )
            for r in wrows
        }

        results.append((market, bets, wallets, cnt))
        print(f"  Loaded market {market_id[:16]}... ({cnt} bets total, {len(bets)} loaded, {len(wallets)} wallets)")

    db.close()
    return results


# ── Run diagnostics ────────────────────────────────────────────────────────────
print("=" * 70)
print("IMPORT STATUS")
print("=" * 70)
for method_id, status in import_results.items():
    print(f"  {method_id:4s}  {status}")

print()
print("=" * 70)
print("LOADING TOP-5 MARKETS")
print("=" * 70)
test_markets = load_data()
print(f"  Loaded {len(test_markets)} markets")

print()
print("=" * 70)
print("RUNNING METHODS")
print("=" * 70)

# Accumulate results per method: list of (market_title, signal, confidence, metadata, error)
all_results = {mid: [] for mid in methods}

for (market, bets, wallets, cnt) in test_markets:
    short_title = market.title[:45] if market.title else market.id[:20]
    print(f"\n  Market: {short_title!r}")
    print(f"  Bets: {len(bets)}  Wallets: {len(wallets)}  Resolved: {market.resolved}  Outcome: {market.outcome}")
    print()

    for method_id, fn in methods.items():
        try:
            result = fn(market, bets, wallets)
            sig = result.signal
            conf = result.confidence
            meta = result.metadata
            err = None
        except Exception as e:
            sig, conf, meta, err = 0.0, 0.0, {}, traceback.format_exc()

        all_results[method_id].append({
            "market": short_title,
            "signal": sig,
            "confidence": conf,
            "metadata": meta,
            "error": err,
        })

        conf_str = f"{conf:.3f}"
        sig_str = f"{sig:+.3f}"
        reason = meta.get("reason", "") if isinstance(meta, dict) else ""
        extra = f" | reason={reason!r}" if reason else ""
        err_flag = " [EXCEPTION]" if err else ""
        print(f"    {method_id:4s}  sig={sig_str}  conf={conf_str}{extra}{err_flag}")

# ── Summary ────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("SUMMARY TABLE")
print("=" * 70)
print(f"  {'Method':<6}  {'AvgConf':>8}  {'MaxConf':>8}  {'AvgSig':>8}  Verdict")
print(f"  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*8}  -------")

verdicts = {}
for method_id, runs in all_results.items():
    if not runs:
        verdicts[method_id] = ("N/A", "No data")
        continue
    confs = [r["confidence"] for r in runs]
    sigs  = [r["signal"]     for r in runs]
    errs  = [r["error"]      for r in runs if r["error"]]
    avg_conf = sum(confs) / len(confs)
    max_conf = max(confs)
    avg_sig  = sum(sigs)  / len(sigs)

    if errs:
        verdict = "BROKEN(exception)"
    elif max_conf == 0.0:
        verdict = "BROKEN(always conf=0)"
    elif avg_conf < 0.05:
        verdict = "THRESHOLD_ISSUE"
    elif avg_conf < 0.20:
        verdict = "DATA_STARVED"
    else:
        verdict = "WORKING"

    verdicts[method_id] = (verdict, avg_conf, max_conf, avg_sig)
    print(f"  {method_id:<6}  {avg_conf:>8.4f}  {max_conf:>8.4f}  {avg_sig:>+8.4f}  {verdict}")

# ── Detailed metadata dump for broken/low-conf methods ────────────────────────
print()
print("=" * 70)
print("DETAILED METADATA (all runs, all methods)")
print("=" * 70)
for method_id, runs in all_results.items():
    print(f"\n--- {method_id} ---")
    for i, r in enumerate(runs):
        print(f"  Market {i+1}: {r['market'][:40]!r}")
        print(f"    signal={r['signal']:+.4f}  confidence={r['confidence']:.4f}")
        if r["error"]:
            print(f"    EXCEPTION:\n{r['error']}")
        else:
            meta = r["metadata"]
            if isinstance(meta, dict):
                for k, v in meta.items():
                    print(f"    {k}: {v}")
            else:
                print(f"    metadata: {meta}")
