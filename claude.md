# OracleBot

## Purpose & Vision

Read-only analytics bot that detects **sharp money** (informed/insider bets) on Polymarket by:
1. Filtering out emotional/irrational bets using behavioral economics
2. Applying 25 detection methods across 6 categories
3. Brute-force testing every method combination for optimal signal extraction
4. Ranking markets by exploitable edge (bot vs. market disagreement)

**This is a research experiment that will involve real money in the future.** The bot currently operates in read-only mode — collecting data, backtesting strategies, and generating daily reports. Once the method combinator achieves consistent edge on resolved markets, the next phase adds automated bet placement via the Polymarket CLOB API. Every design decision prioritizes accuracy and robustness because incorrect signals cost real capital.

**No bet placement is implemented. This is strictly analytics.**

---

## How to Run / Test

```bash
# Run the test suite (33 tests, no API/DB calls)
pytest tests/ -v

# Initialize DB and run a pipeline smoke test
python main.py init
python test_pipeline.py

# CLI modes
python main.py collect    # scrape markets + trades
python main.py analyze    # run combinator + report
python main.py run        # both (scheduled loop)

# Live dashboard
python caretaker.py       # or oracle.bat on Windows
```

All constants: `config.py` · Agent specs: `docs/agents.md` · Bug history: `docs/PROCESS_LOG.md` · Method algorithms: `methods/CLAUDE.md`

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11+ (installed at `C:\Python314`) | Core runtime |
| Database | SQLite (WAL mode, ~787MB) | Single-file storage, no server dependency |
| Terminal UI | `rich` | Live dashboard with panels, tables, progress bars |
| HTTP | `requests` | API calls with retry/backoff |
| Math | `numpy`, `scipy.stats` | Statistical methods (z-scores, chi-squared, correlation) |
| Graphs | `networkx`, `python-louvain` | Wallet coordination clustering (S3) |
| Scheduling | `schedule` | Recurring collection/analysis cycles |
| Charts | `plotly` | Interactive HTML visualizations (data-analyst agent) |
| Env Config | `python-dotenv` | `.env` file loading for API keys |
| Platform | Windows 10, Git Bash sandbox | Dev environment |

### Active API Dependencies

| API | Base URL | Auth | Pagination | Purpose |
|-----|----------|------|------------|---------|
| **Gamma** | `gamma-api.polymarket.com/markets` | None | Offset (`offset`, `limit`) | Market discovery (richest metadata) |
| **Data** | `data-api.polymarket.com/trades` | None | Offset (hard cap ~3500) | Public trade history |
| **CLOB** | `clob.polymarket.com` | None (read) | Cursor (`next_cursor`, `MA==` start, `LTE=` end) | Orderbook, pricing, resolved outcomes |
| **Polygonscan** | `api.polygonscan.com/api` | API key | Page-based | On-chain wallet transactions (optional) |

**Data hierarchy:** Event → Market(s) → Outcome Token(s). Always resolve down to `token_id` for price/orderbook queries.

**Rate limits:** Gamma ~10 req/s (cache 5 min), CLOB ~10 req/s (cache 1 min), Data ~5 req/s (cache 5 min).

---

## Method Interface

Every method: `(Market, list[Bet], dict[str, Wallet]) -> MethodResult(signal, confidence, filtered_bets, metadata)`
- **signal**: -1.0 (strong NO) to +1.0 (strong YES)
- **confidence**: 0.0 (no information) to 1.0 (certain)
- **filtered_bets**: bets after removing noise (passed to next method in chain)
- **metadata**: diagnostic info (thresholds, counts, intermediate values)

### Signal Aggregation

Methods in a combo run sequentially — each receives the previous method's `filtered_bets`. Final signal is confidence-weighted average:
```
signal = sum(r.signal * r.confidence for r in results) / sum(r.confidence for r in results)
confidence = sum(r.confidence for r in results) / len(results)
```

---

## Detection Methods (25 total)

> Full algorithm details (thresholds, formulas, deps): `methods/CLAUDE.md`

| ID | Name | Detects |
|----|------|---------|
| **S1** | Win Rate Outlier | Wallets with statistically abnormal win rates |
| **S3** | Coordination Clustering | Coordinated wallet groups (Louvain, networkx+louvain) |
| **S4** | Sandpit Filter | Bait/trap accounts — removes them from signal |
| **D5** | Vacuous Truth | Markets already near-certain (≥0.95 or ≤0.05 odds) |
| **D7** | Pigeonhole Noise | Too many "sharp" wallets → noise discount |
| **D8** | Boolean SAT | Structural bet distribution skew (≥80% one side) |
| **D9** | Set Partition | Separates rational bets from emotional (master filter) |
| **E10** | Loyalty Bias | Wallets that always bet the same side |
| **E11** | Recency Bias | Early bets extrapolating from recent events |
| **E12** | Revenge Betting | Tilt/chase: bet size escalating after losses |
| **E13** | Hype Detection | Volume spikes from media/social attention |
| **E14** | Odds Sensitivity | Flat betting regardless of edge (no odds adjustment) |
| **E15** | Round Numbers | Emotional round-amount bets ($50/$100/$500) |
| **E16** | KL Divergence | Wallets with extreme YES/NO directional skew |
| **T17** | Bayesian Updating | Smart money vs. public opinion divergence (scipy) |
| **T18** | Benford's Law | Manufactured/coordinated bet amounts via chi-squared (scipy) |
| **T19** | Z-Score Outlier | Statistically unusual bet sizes × rationality |
| **P20** | Nash Deviation | Price divergence from VWAP equilibrium |
| **P21** | Prospect Theory | Kahneman/Tversky probability weighting mispricing |
| **P22** | Herding | Temporal clustering of same-side bets (O(n) two-pointer) |
| **P23** | Anchoring | Market price stuck on the first large bet's anchor |
| **P24** | Wisdom vs Madness | % emotional bets → market exploitability meta-signal |
| **M26** | Market Phases | Trending vs. mean-reverting price dynamics (Markov) |
| **M27** | Flow Momentum | Persistent directional bet flow vs. oscillation (Markov) |
| **M28** | Smart-Follow | Smart money leading retail in temporal order (Markov) |

---

## Engine Pipeline

### Fitness Function
```
fitness = accuracy * 0.35 + edge_vs_market * 0.35 - false_positive_rate * 0.20 - (complexity / TOTAL_METHODS) * 0.10
```
- **accuracy**: % of resolved markets predicted correctly
- **edge_vs_market**: how often the combo beats raw market odds
- **false_positive_rate**: high-confidence wrong predictions / total high-confidence predictions
- **complexity**: number of methods in combo (penalized to prefer parsimony)

### Backtesting
- Replays resolved markets using only bets visible before a `BACKTEST_CUTOFF_FRACTION` of market lifespan
- Caps bets per market at 500 (prevents O(n^2) in graph methods)
- Per-market wallet filtering (never passes 140k+ wallets to methods)
- Normalizes odds: `b.odds if b.side == "YES" else (1 - b.odds)`

### Combinator (3-Tier Brute Force)
- **Tier 1**: Within-category combos (singles, pairs, triples). Max combo size = 3.
- **Tier 2**: Cross-category pairs and triples of Tier 1 finalists only (NOT all 2^N subsets).
- **Tier 3**: Hill-climb on top 3 seeds (greedy add/remove).
- `prune_method_results(keep=50)` after each full optimization.
- `flush_method_results()` after each tier.

### Report & Pick Ranking
- Picks ranked by **edge**: `abs(bot_prob - market_price) * confidence`
- `bot_prob = 0.5 + signal * 0.5` maps signal to probability
- Filters: no extreme prices (YES <5% or >95%), no edge <0.01
- Output: markdown report + rich terminal display

---

## Key Rules

- **READ-ONLY. No betting.**
- SQLite only. Connection uses `timeout=30` for WAL mode.
- All timestamps UTC.
- API retries with exponential backoff (`API_MAX_RETRIES`, `API_RETRY_BACKOFF`).
- Trade pagination capped at 7 pages (Data API hard limit at ~3500 offset).
- Wallet stats computed via SQL aggregation, not Python loops. Batch with `executemany` + single `commit`.
- `gc.collect()` between analysis phases. `del` large dicts when done.
- Active trade fetches capped at 500/cycle, resolved at 100/cycle.
- Bets per market capped at 500 in backtest to prevent O(n^2) in graph methods.
- Log everything to `bot.log`. Dashboard uses `rich` for console — no logging to stdout.

---

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
- `upsert_market()` has no internal commit — callers (both `main.py` AND `dashboard.py`) must call `conn.commit()` after their market upsert loops. **On Windows, running DB writes inside a `console.status()` Rich spinner block can starve the SQLite timeout polling and cause indefinite hangs** — always keep upsert loops outside spinner/progress contexts.

### Graph Method Performance
- S3 (Louvain): min bets = 10 to skip expensive graph ops on tiny datasets.
- E13: use `set` membership for spike bet filtering, not list (O(1) vs O(n)).
- Backtest caches method function lookups once per combo, not per market.
- Use Python `statistics.median` instead of `numpy.median` for small arrays (faster, no numpy overhead).

---

## Database Schema

```sql
markets(id TEXT PK, title, description, end_date, resolved BOOL, outcome, created_at)
bets(id INTEGER PK AUTO, market_id FK, wallet, side, amount, odds, timestamp)
  -- Indexes: idx_bets_market, idx_bets_wallet, idx_bets_timestamp, idx_bets_unique
wallets(address TEXT PK, first_seen, total_bets, total_volume, win_rate, rationality_score, flagged_suspicious, flagged_sandpit)
wallet_relationships(wallet_a, wallet_b PK, relationship_type, confidence)
method_results(id INTEGER PK AUTO, combo_id UNIQUE, methods_used JSON, accuracy, edge_vs_market, false_positive_rate, complexity, fitness_score, tested_at)
  -- Index: idx_mr_combo_unique
holdout_validation(id INTEGER PK AUTO, combo_id, train_markets, holdout_markets, train_fitness, holdout_fitness, tested_at)
```
