# Polymarket Prediction Bot

Read-only analytics bot. Detects sharp/insider money on Polymarket by filtering emotional bets, applying statistical methods, and brute-force testing method combinations. **No bet placement.**

## Stack
Python 3.11+ / SQLite / rich / Polymarket CLOB + Gamma + Data APIs / Polygon on-chain

## Structure
```
config.py           — constants, API endpoints, method thresholds
main.py             — CLI entry point + scheduler (collect/analyze/run/init)
dashboard.py        — visual terminal dashboard (rich), main runtime loop
caretaker.py        — watchdog that auto-restarts dashboard on crash
PBCareTaker.bat     — Windows launcher for caretaker
data/models.py      — dataclasses: Market, Bet, Wallet, MethodResult, ComboResults
data/db.py          — SQLite schema + CRUD + dedup migrations
data/scraper.py     — API ingestion (Gamma=markets, Data API=trades, CLOB=orderbook)
methods/__init__.py — registry (24 methods, decorator-based)
methods/suspicious.py   — S1-S4
methods/discrete.py     — D5-D9
methods/emotional.py    — E10-E16
methods/statistical.py  — T17-T19
methods/psychological.py — P20-P24
engine/fitness.py    — scoring: accuracy*0.35 + edge*0.35 - FPR*0.20 - complexity*0.10
engine/backtest.py   — replay resolved markets through method combos
engine/combinator.py — Tier1 (within-category) → Tier2 (cross-category) → Tier3 (hill-climb)
engine/report.py     — daily markdown report + top picks with edge scoring
```

## Method Interface
Every method: `(Market, list[Bet], dict[str, Wallet]) -> MethodResult(signal, confidence, filtered_bets, metadata)`
- signal: -1.0 (NO) to +1.0 (YES)
- confidence: 0.0 to 1.0

## APIs
- **Gamma** (`gamma-api.polymarket.com/markets`): market discovery, offset pagination
- **Data** (`data-api.polymarket.com/trades`): public trades, offset pagination, hard cap ~3500 offset
- **CLOB** (`clob.polymarket.com`): orderbook, pricing, cursor pagination (`next_cursor`)
- **CLOB markets** have `tokens[].winner` for resolved outcome data

## Key Rules
- READ-ONLY. No betting.
- SQLite only. No external DB. Connection uses `timeout=30` for WAL mode.
- All timestamps UTC.
- API retries with exponential backoff.
- Trade pagination capped at 7 pages (API hard limit).
- Wallet stats computed via SQL aggregation, not Python loops. Batch with `executemany` + single `commit`.
- `gc.collect()` between analysis phases. `del` large dicts when done.
- Active trade fetches capped at 500/cycle, resolved at 100/cycle.
- Bets per market capped at 500 in backtest to prevent O(n^2) in graph methods.
- Log everything to `bot.log`. Dashboard uses `rich` for console — no logging to stdout.

## Data Integrity Rules (Bug Fixes Applied)

### Odds Normalization
- `Bet.odds` MUST always store the **YES probability** (0.0-1.0), never the raw token price.
- In `scraper.py _parse_trade()`: YES-token trades store price as-is; NO-token trades store `1 - price`.
- When reading existing data that may have old mixed odds, normalize: `b.odds if b.side == "YES" else (1 - b.odds)`.
- NEVER average raw `b.odds` across mixed YES/NO bets without normalizing first.

### Deduplication
- `bets` table has UNIQUE index on `(market_id, wallet, side, amount, timestamp)`. `INSERT OR IGNORE` deduplicates.
- `method_results` table has UNIQUE on `combo_id`. Upsert keeps the better fitness score.
- `db.init_db()` runs migration on first startup: deduplicates existing rows, then creates indexes.

### Combinator Caps (Prevent Combinatorial Explosion)
- Tier 1: max combo size = 3 (within-category singles, pairs, triples).
- Tier 2: pairs and triples of Tier 1 finalists only. NOT all 2^N subsets.
- Tier 3: hill-climb only the top 3 seeds.
- `prune_method_results(keep=50)` after each full optimization — table does not grow unbounded.
- `flush_method_results()` (commit) after each tier.

### Per-Market Wallet Filtering
- NEVER pass the full wallet dict (140k+) to methods or report scoring.
- Always filter to wallets that appear in the current market's bets: `{b.wallet: wallets[b.wallet] for b in bets if b.wallet in wallets}`.
- This applies in `backtest.py`, `report.py`, and anywhere methods are called.

### Pick Ranking (Edge Over Market)
- Picks ranked by **edge**: `abs(bot_prob - market_price) * confidence`, NOT raw conviction.
- `bot_prob = 0.5 + signal * 0.5` maps signal to probability.
- Filter out markets at extreme prices (YES < 5% or > 95%) — these are settled, not opportunities.
- Filter out picks with edge < 0.01.

### Database Locking Prevention
- Use `sqlite3.connect(path, timeout=30)` — never default timeout.
- Batch all bulk writes with `executemany` + single `conn.commit()`. Never commit per-row.
- Removed per-row commit from `insert_method_result` — use `flush_method_results()` to batch.

### Graph Method Performance
- S3 (Louvain) and D6 (PageRank): min bets = 10 to skip expensive graph ops on tiny datasets.
- E13: use `set` membership for spike bet filtering, not list (O(1) vs O(n)).
- Backtest caches method function lookups once per combo, not per market.
- Use Python `statistics.median` instead of `numpy.median` for small arrays (faster, no numpy overhead).
