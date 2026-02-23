"""
Read-only database summary for data-analyst agent.
All queries are SELECT only.
"""
import sqlite3

DB = 'D:/Developer/Personal/Bots/PolyMarketTracker/data.db'
conn = sqlite3.connect(DB, timeout=30)
cur = conn.cursor()

# 1. Markets: total, resolved vs unresolved
cur.execute(
    "SELECT COUNT(*), "
    "SUM(CASE WHEN resolved=1 THEN 1 ELSE 0 END), "
    "SUM(CASE WHEN resolved=0 OR resolved IS NULL THEN 1 ELSE 0 END) "
    "FROM markets"
)
mkt = cur.fetchone()
print("=== 1. MARKETS ===")
print(f"  Total:      {mkt[0]}")
print(f"  Resolved:   {mkt[1]}")
print(f"  Unresolved: {mkt[2]}")

# 2. Bets: total, date range
cur.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM bets")
b = cur.fetchone()
print()
print("=== 2. BETS ===")
print(f"  Total:      {b[0]}")
print(f"  Earliest:   {b[1]}")
print(f"  Latest:     {b[2]}")

# 3. Unique wallets
cur.execute("SELECT COUNT(*) FROM wallets")
w = cur.fetchone()
print()
print("=== 3. WALLETS ===")
print(f"  Unique wallets tracked: {w[0]}")

# 4. Top 5 markets by bet count
cur.execute(
    "SELECT m.title, COUNT(b.id) as bet_count "
    "FROM bets b "
    "JOIN markets m ON b.market_id = m.id "
    "GROUP BY b.market_id "
    "ORDER BY bet_count DESC "
    "LIMIT 5"
)
rows = cur.fetchall()
print()
print("=== 4. TOP 5 MARKETS BY BET COUNT ===")
for row in rows:
    title = (row[0] or "Unknown")[:80]
    print(f"  {row[1]:>6} bets | {title}")

# 5. Bet volume distribution
cur.execute(
    "SELECT "
    "  SUM(amount) as total_volume, "
    "  AVG(amount) as avg_bet, "
    "  MIN(amount) as min_bet, "
    "  MAX(amount) as max_bet, "
    "  COUNT(*) as total_bets "
    "FROM bets"
)
vol = cur.fetchone()
print()
print("=== 5. BET VOLUME DISTRIBUTION (USDC) ===")
print(f"  Total Volume: {vol[0]:,.2f}" if vol[0] else "  Total Volume: 0")
print(f"  Avg Bet:      {vol[1]:,.2f}" if vol[1] else "  Avg Bet: 0")
print(f"  Min Bet:      {vol[2]:,.2f}" if vol[2] else "  Min Bet: 0")
print(f"  Max Bet:      {vol[3]:,.2f}" if vol[3] else "  Max Bet: 0")

# Volume by side breakdown
cur.execute(
    "SELECT side, COUNT(*), SUM(amount) "
    "FROM bets "
    "GROUP BY side"
)
print("  By side:")
for row in cur.fetchall():
    print(f"    {row[0]}: {row[1]} bets, {row[2]:,.2f} USDC" if row[2] else f"    {row[0]}: {row[1]} bets")

# Volume bucket distribution
cur.execute(
    "SELECT "
    "  SUM(CASE WHEN amount < 10 THEN 1 ELSE 0 END) as under10, "
    "  SUM(CASE WHEN amount >= 10 AND amount < 50 THEN 1 ELSE 0 END) as b10_50, "
    "  SUM(CASE WHEN amount >= 50 AND amount < 100 THEN 1 ELSE 0 END) as b50_100, "
    "  SUM(CASE WHEN amount >= 100 AND amount < 500 THEN 1 ELSE 0 END) as b100_500, "
    "  SUM(CASE WHEN amount >= 500 AND amount < 1000 THEN 1 ELSE 0 END) as b500_1k, "
    "  SUM(CASE WHEN amount >= 1000 THEN 1 ELSE 0 END) as over1k "
    "FROM bets"
)
bk = cur.fetchone()
print("  Bet size buckets:")
labels = ["<10", "10-50", "50-100", "100-500", "500-1000", ">1000"]
for label, count in zip(labels, bk):
    print(f"    {label:>10}: {count} bets")

# 6. Method results count
cur.execute("SELECT COUNT(*), MAX(fitness_score), AVG(fitness_score) FROM method_results")
mr = cur.fetchone()
print()
print("=== 6. METHOD RESULTS (COMBINATOR PROGRESS) ===")
print(f"  Total combos tested: {mr[0]}")
if mr[0] and mr[0] > 0:
    print(f"  Best fitness score:  {mr[1]:.4f}" if mr[1] is not None else "  Best fitness score: N/A")
    print(f"  Avg fitness score:   {mr[2]:.4f}" if mr[2] is not None else "  Avg fitness score:  N/A")
    cur.execute(
        "SELECT methods_used, fitness_score, accuracy, edge_vs_market "
        "FROM method_results "
        "ORDER BY fitness_score DESC "
        "LIMIT 3"
    )
    top = cur.fetchall()
    print("  Top 3 combos by fitness:")
    for row in top:
        print(f"    Methods: {row[0]} | fitness={row[1]:.4f} accuracy={row[2]:.4f} edge={row[3]:.4f}")

# 7. Wallet relationships
cur.execute("SELECT COUNT(*), COUNT(DISTINCT relationship_type) FROM wallet_relationships")
wr = cur.fetchone()
print()
print("=== 7. WALLET RELATIONSHIPS ===")
print(f"  Total relationships recorded: {wr[0]}")
if wr[0] and wr[0] > 0:
    cur.execute("SELECT relationship_type, COUNT(*), AVG(confidence) FROM wallet_relationships GROUP BY relationship_type")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]} pairs, avg confidence={row[2]:.3f}")

conn.close()
print()
print("Done.")
