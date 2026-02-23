# OracleBot

## Purpose & Vision

Read-only analytics bot that detects **sharp money** (informed/insider bets) on Polymarket by:
1. Filtering out emotional/irrational bets using behavioral economics
2. Applying 28 detection methods across 6 categories
3. Brute-force testing every method combination for optimal signal extraction
4. Ranking markets by exploitable edge (bot vs. market disagreement)

**This is a research experiment that will involve real money in the future.** The bot currently operates in read-only mode — collecting data, backtesting strategies, and generating daily reports. Once the method combinator achieves consistent edge on resolved markets, the next phase adds automated bet placement via the Polymarket CLOB API. Every design decision prioritizes accuracy and robustness because incorrect signals cost real capital.

**No bet placement is implemented. This is strictly analytics.**

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11+ (installed at `C:\Python314`) | Core runtime |
| Database | SQLite (WAL mode, ~787MB) | Single-file storage, no server dependency |
| Terminal UI | `rich` | Live dashboard with panels, tables, progress bars |
| HTTP | `requests` | API calls with retry/backoff |
| Math | `numpy`, `scipy.stats` | Statistical methods (z-scores, chi-squared, correlation) |
| Graphs | `networkx`, `python-louvain` | Wallet coordination clustering (S3, D6) |
| Scheduling | `schedule` | Recurring collection/analysis cycles |
| Charts | `plotly` | Interactive HTML visualizations (data-analyst agent) |
| Env Config | `python-dotenv` | `.env` file loading for API keys |
| Async HTTP | `aiohttp`, `websockets` | WebSocket streams, async data collection (planned) |
| Polymarket SDK | `py-clob-client` | Official CLOB read-only client (planned) |
| Platform | Windows 10, Git Bash sandbox | Dev environment |

### Active API Dependencies

| API | Base URL | Auth | Pagination | Purpose |
|-----|----------|------|------------|---------|
| **Gamma** | `gamma-api.polymarket.com/markets` | None | Offset (`offset`, `limit`) | Market discovery (richest metadata) |
| **Data** | `data-api.polymarket.com/trades` | None | Offset (hard cap ~3500) | Public trade history |
| **CLOB** | `clob.polymarket.com` | None (read) | Cursor (`next_cursor`, `MA==` start, `LTE=` end) | Orderbook, pricing, resolved outcomes |
| **Polygonscan** | `api.polygonscan.com/api` | API key | Page-based | On-chain wallet transactions (optional) |

**Data hierarchy:** Event → Market(s) → Outcome Token(s). Always resolve down to `token_id` for price/orderbook queries.

**Rate limits:** Gamma ~10 req/s (cache 5 min), CLOB ~10 req/s (cache 1 min), Data ~5 req/s (cache 5 min), WebSocket 5 connections.

**Unintegrated endpoints:** price, midpoint, spread, tick-size, last-trade-price, search, tags, events, activity, positions, leaderboard, WebSocket stream.

**Client libs:** `py-clob-client` — `ClobClient("https://clob.polymarket.com")` no private key. `polymarket-apis` — unified Gamma+CLOB+Data+WebSocket wrapper.

**Phase 2 source APIs (not yet integrated):** FRED (`fredapi`, `FEDFUNDS`/`CPIAUCSL`/etc.), NOAA/NWS (`api.weather.gov`), NCEI (historical weather), CoinGecko (`pycoingecko`), ESPN (unofficial), The Odds API, GovTrack.

### Config Constants (defined in config.py)

**API**: `API_MAX_RETRIES`, `API_RETRY_BACKOFF`, `API_REQUEST_TIMEOUT`, `GAMMA_MARKETS_ENDPOINT`, `POLYMARKET_MARKETS_ENDPOINT`, `POLYMARKET_BASE_URL`, `POLYGONSCAN_API_KEY`, `POLYGONSCAN_BASE_URL`

**Engine**: `FITNESS_W_ACCURACY=0.35`, `FITNESS_W_EDGE=0.35`, `FITNESS_W_FALSE_POS=0.20`, `FITNESS_W_COMPLEXITY=0.10`, `BACKTEST_CUTOFF_FRACTION`, `TIER1_TOP_PER_CATEGORY`, `TIER2_TOP_OVERALL`, `SCRAPE_INTERVAL_MINUTES`, `DB_PATH`

**Method thresholds**: `S1_MIN_RESOLVED_BETS`, `S1_STDDEV_THRESHOLD`, `S2_LATE_STAGE_FRACTION`, `S2_HIGH_CONVICTION_ODDS`, `S3_TIME_WINDOW_MINUTES`, `S3_MIN_CLUSTER_SIZE`, `S4_SANDPIT_MIN_BETS`, `S4_SANDPIT_MAX_WIN_RATE`, `S4_SANDPIT_MIN_VOLUME`, `S4_NEW_WALLET_MAX_BETS`, `S4_NEW_WALLET_LARGE_BET`, `D7_MIN_BETS`, `E10_MIN_MARKETS`, `E10_CONSISTENCY_THRESHOLD`, `E12_WINDOW_HOURS`, `E13_VOLUME_SPIKE_MULTIPLIER`, `E14_LOW_CORRELATION_THRESHOLD`, `E15_ROUND_DIVISOR`, `E16_KL_THRESHOLD`, `T17_AMOUNT_NORMALIZER`, `T17_UPDATE_STEP`, `T17_RATIONALITY_CUTOFF`, `T18_CHI_SQUARED_PVALUE`, `T19_ZSCORE_THRESHOLD`, `P20_DEVIATION_THRESHOLD`, `P21_LOW_PROB`, `P21_HIGH_PROB`, `P22_MIN_HERD_SIZE`, `P22_TIME_WINDOW_MINUTES`, `P23_ANCHOR_MIN_AMOUNT`, `P24_HIGH_RATIO`, `P24_LOW_RATIO`, `M25_MIN_WALLET_BETS`, `M25_SMALL_MULTIPLIER`, `M25_LARGE_MULTIPLIER`, `M25_ESCALATION_THRESHOLD`, `M25_CONFIDENCE_CAP`, `M26_NUM_WINDOWS`, `M26_LOW_THRESHOLD`, `M26_HIGH_THRESHOLD`, `M26_TRENDING_THRESHOLD`, `M27_NUM_WINDOWS`, `M27_FLOW_THRESHOLD`, `M27_MOMENTUM_THRESHOLD`, `M28_SMART_THRESHOLD`, `M28_RETAIL_THRESHOLD`, `M28_NUM_WINDOWS`, `M28_MIN_SMART_WALLETS`, `M28_MIN_RETAIL_WALLETS`, `REPORT_PRICE_RECENT_TRADES`, `REPORT_PRICE_MIN_TRADES`, `TOTAL_METHODS`

---

## Project Structure

```
config.py               — constants, API endpoints, all method thresholds
main.py                 — CLI entry (collect/analyze/run/init) + scheduler
dashboard.py            — rich terminal dashboard, main runtime loop
caretaker.py            — watchdog: auto-restarts dashboard on crash
oracle.bat              — Windows launcher for caretaker

data/
  models.py             — dataclasses: Market, Bet, Wallet, MethodResult, ComboResults, WalletRelationship
  db.py                 — SQLite schema, CRUD, dedup migrations, WAL mode
  scraper.py            — API ingestion (Gamma=markets, Data=trades, CLOB=orderbook, Polygonscan=on-chain)

methods/
  __init__.py           — registry (28 methods, @register decorator, MethodFn type)
  suspicious.py         — S1-S4: wallet-level anomaly detection
  discrete.py           — D5-D9: mathematical structure analysis
  emotional.py          — E10-E16: behavioral bias filtering
  statistical.py        — T17-T19: statistical outlier detection
  psychological.py      — P20-P24: market psychology signals
  markov.py             — M25-M28: Markov chain temporal transition analysis
  CLAUDE.md             — full algorithm specs for all 28 methods

engine/
  fitness.py            — scoring: accuracy*0.35 + edge*0.35 - FPR*0.20 - complexity*0.10
  backtest.py           — replay resolved markets through method combos
  combinator.py         — Tier1 (within-category) → Tier2 (cross-category) → Tier3 (hill-climb)
  report.py             — daily markdown report + top picks ranked by edge

scripts/
  validate_readonly_query.py — safety hook: blocks SQL writes from data-analyst agent

analysis/                — reusable analysis scripts (created by data-analyst agent)
reports/                 — daily markdown reports + plotly HTML charts
docs/
  PROCESS_LOG.md         — development journal + resolved bug history
  agents.md              — full specs: backtest-analyst, debug-doctor, stub agents
```

### Data Flow

```
Gamma API ──→ scraper.py ──→ db.py (markets table)
Data API  ──→ scraper.py ──→ db.py (bets table)
CLOB API  ──→ scraper.py ──→ db.py (resolved outcomes)
                                │
                    ┌───────────┘
                    ▼
              main.py / dashboard.py
                    │
          ┌─────────┼──────────┐
          ▼         ▼          ▼
   update_wallet  methods/   backtest.py
   _stats (SQL)   *.py       (resolved markets)
          │         │              │
          ▼         ▼              ▼
     wallets    MethodResult  combinator.py
     table      (signal,      Tier1→Tier2→Tier3
                confidence)        │
                    │              ▼
                    └──────→ report.py
                             (edge-ranked picks)
                                   │
                                   ▼
                            dashboard.py
                            (rich display)
```

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

## Detection Methods (28 total)

> Full algorithm details (thresholds, formulas, deps): `methods/CLAUDE.md`

| ID | Name | Detects |
|----|------|---------|
| **S1** | Win Rate Outlier | Wallets with statistically abnormal win rates |
| **S2** | Bet Timing | Late-stage high-conviction bets (insider timing) *(excluded)* |
| **S3** | Coordination Clustering | Coordinated wallet groups (Louvain, networkx+louvain) |
| **S4** | Sandpit Filter | Bait/trap accounts — removes them from signal |
| **D5** | Vacuous Truth | Markets already near-certain (≥0.95 or ≤0.05 odds) |
| **D6** | PageRank | Influential wallets in the copy-trading graph (networkx) *(excluded)* |
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
| **M25** | Wallet Regime | Bet size escalation per wallet (informed accumulation) *(excluded)* |
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

## GUI Roadmap

**Current:** Rich terminal dashboard (`dashboard.py`). **V1 (planned):** Streamlit web dashboard.

**Pages:** Dashboard · Markets · Wallets · Method Performance · Combo Results · Reports · Settings

**Color scheme:**
- YES: `#22c55e` · NO: `#ef4444` · Neutral: `#6b7280` · Emotional: `#f59e0b` · Rational: `#3b82f6` · Suspicious: `#a855f7` · Sandpit: `#dc2626`
- Categories: S=`#a855f7` · D=`#3b82f6` · E=`#f59e0b` · T=`#22c55e` · P=`#ec4899` · M=`#06b6d4`

**Tech:** `streamlit` + `plotly` + `streamlit-autorefresh`. Backend reads from same SQLite DB.

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
- **Cache aggressively.** Market lists: 5 min. Prices: 1 min. Historical data: 1 hour. Wallet profiles: 5 min.
- **Wallet tracking strategy.** Seed from Data API leaderboard. Deep-dive `/activity` history. Track wallets consistently appearing in sharp-money methods.
- **Source data timing.** NOAA updates 4x/day. FRED release dates: BLS = first Friday, CPI = ~10th.

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

### Graph Method Performance
- S3 (Louvain) and D6 (PageRank): min bets = 10 to skip expensive graph ops on tiny datasets.
- E13: use `set` membership for spike bet filtering, not list (O(1) vs O(n)).
- Backtest caches method function lookups once per combo, not per market.
- Use Python `statistics.median` instead of `numpy.median` for small arrays (faster, no numpy overhead).

---

## Token Efficiency Rules

### For Claude (self-instructions)
- **Read before writing.** Never guess file contents. Read the actual file, then edit surgically.
- **Use Edit over Write.** Edit changes specific lines; Write replaces entire files and sends all content through the context.
- **Parallel tool calls.** When reading multiple independent files, read them all in one message.
- **Don't re-read.** If a file was read earlier in the conversation and hasn't changed, don't read it again.
- **Grep before Read.** If looking for something specific, Grep first to find the file/line, then Read only the relevant section with offset/limit.
- **Glob before Grep.** If unsure which files exist, Glob the pattern first. Don't Grep the entire codebase.
- **Delegate to agents** for self-contained research or analysis tasks. This keeps the main context lean.
- **Concise responses.** Don't repeat code back to the user. Reference it by file:line.
- **Batch commits.** Stage specific files, not `git add -A`. Write commit messages via HEREDOC.
- **Don't over-document.** No docstrings, comments, or type annotations on code you didn't change.

### For the User
- Be specific in requests. "Fix the bug in S3 where clusters of size 2 are flagged" is better than "fix S3."
- Reference files by name. "Update `scraper.py:_parse_trade`" saves a search.
- Use agents for research: ask `search-specialist` to investigate before asking for code changes.
- Use `task-decomposer` for complex work — the plan prevents wasted implementation cycles.

---

## Bug Tracking

> Resolved bugs (B001-B017): `docs/PROCESS_LOG.md`

### Known Issues / Potential Bugs

| ID | Module | Risk | Description |
|----|--------|------|-------------|
| P004 | `psychological.py` P21 | Low | Prospect theory weighting function may not match original Tversky-Kahneman formula exactly |
| P006 | `report.py` | Low | `Wallet(address="")` placeholder for missing wallets in emotion ratio calc — could cause issues if Wallet fields are accessed |
| P011 | `scraper.py` | Medium | No caching layer — repeated API calls for same data within a cycle waste rate limit budget |
| P012 | `scraper.py` | Low | `fetch_trades_for_market` uses Data API but leaderboard/activity endpoints not integrated — missing wallet seeding |
| P015 | `scraper.py` | Low | WebSocket not implemented — only REST polling. Real-time data would improve detection latency |

### Areas Needing Review

| Area | Priority | Notes |
|------|----------|-------|
| Wallet rationality formula | Medium | `win_rate * 0.5 + (1 - round_ratio) * 0.3 + 0.2` — weights are arbitrary. Needs validation against backtest data. |
| Method independence | Medium | Some methods may be highly correlated (e.g., E10 loyalty + E16 KL divergence). Correlated methods in a combo don't add information but increase complexity penalty. |
| Edge calculation precision | Medium | `bot_prob = 0.5 + signal * 0.5` is a linear mapping. May not accurately represent probability when multiple methods disagree. |
| Data API offset cap | Low | Hard cap at ~3500 offset means markets with >3500 trades have incomplete data. May bias toward smaller markets. |
| S3/D6 graph scalability | Low | O(n^2) edge building. Cap at 500 bets helps. Consider time-window pruning for very active markets. |
| Test coverage | Medium | `test_pipeline.py` exists but unclear scope. Methods need unit tests with known-outcome fixtures. |
| API caching layer | Medium | No caching between cycles. Market lists, prices, wallet data should be cached with TTLs. |
| Leaderboard wallet seeding | Medium | Data API `/leaderboard` not used. Should seed wallet tracking from consistently profitable wallets. |
| WebSocket integration | Low | All collection is REST polling. WebSocket enables real-time E13 spike detection and faster S2 signals. |
| Source data integration | Low | FRED, NOAA, CoinGecko, ESPN not yet integrated. |
| GUI migration | Low | Terminal dashboard works but limits access. Streamlit V1 would enable remote monitoring. |
| `.env` for secrets | Medium | `POLYGONSCAN_API_KEY` read from env but no `.env` file or `python-dotenv` setup. |

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
```

---

## Agent Delegation Rules

**Claude is the director, not the builder.** The job is to read context, make decisions, and delegate execution to agents and skills. Build directly only for trivial changes. Every task delegated to an agent preserves main context and runs faster. Default to delegation — justify doing it yourself, not the other way around.

> Full agent specs (capabilities, I/O format, checklists, examples): `docs/agents.md`

### Chain Patterns by Work Type

| Work Type | Chain | Notes |
|-----------|-------|-------|
| Tiny fix | Direct → done | <20 lines, single file, cause is obvious. If unsure, it's not tiny. |
| Medium code change | Direct → `debug-doctor` | 1-3 files, clear requirements. If scope is unclear or >3 files, escalate to `task-decomposer`. |
| Vague / complex input | `task-decomposer` (clarify) → `task-decomposer` (decompose) → agents | Diagrams, ambiguous specs, extended context. Decomposer runs Phase 0 clarification before planning. |
| Bug investigation | `debug-doctor` → direct or `task-decomposer` | Doctor triages first. "Complex" = root cause spans >1 module or is unknown after log inspection. |
| New feature / new method | `task-decomposer` → direct/agents → `debug-doctor` | Always plan before building. No exceptions. |
| Multi-file restructure | `task-decomposer` → direct/agents → `debug-doctor` | Never restructure without a plan. |
| Schema migration / DB change | `task-decomposer` → direct → `debug-doctor` | Irreversible. Requires explicit backup step in the plan. |
| Data question / metric | `data-analyst` → report | Never query DB directly in main session. |
| Research that feeds a plan | `search-specialist` → `task-decomposer` → agents | Chain when research output is input to a plan, not just a lookup. |
| Pure research / lookup | `search-specialist` → report | Codebase, web, git history, API docs — no follow-on planning needed. |
| Backtest interpretation | `backtest-analyst` → action | M1 milestone — ready now. |
| Method quality audit | `method-auditor` → `threshold-tuner` (if sensitivity found) | M2 milestone. Auditor identifies dead-weight and correlated methods. |
| Threshold sensitivity | `method-auditor` → `threshold-tuner` | M3 milestone. Auditor identifies issue, tuner optimizes. |
| Wallet investigation | `wallet-profiler` | M5 milestone. |
| Agent / prompt writing | `prompt-engineer` (new agent) or direct (minor wording) | New agent definitions always go through prompt-engineer. |
| Post-change validation | `debug-doctor` | Always — after any method, engine, or scraper change. |
| GUI / Streamlit change | Direct → `debug-doctor` | UI-only. Run import + smoke test after. |

### Routing Table

| Task Type | Agent | Examples |
|-----------|-------|---------|
| Prompt writing/refinement | `prompt-engineer` | Write agent system prompts, improve method descriptions |
| Research & information gathering | `search-specialist` | Find API rate limits, trace data flow, look up library docs |
| Complex task planning & requirements clarification | `task-decomposer` | Plan new method implementation, design schema migration, interpret vague/diagram input before decomposing |
| Data analysis & visualization | `data-analyst` | Query bet distributions, chart wallet activity, method performance metrics |
| Backtest interpretation | `backtest-analyst` | Interpret optimization results, method contributions, combo diagnostics |
| Method quality review | `method-auditor` | Method orthogonality, implementation validation, dead-weight detection |
| Threshold optimization | `threshold-tuner` | Config constant sensitivity analysis, parameter optimization |
| API reliability | `api-health-checker` | Ping endpoints, validate schemas, monitor rate limits |
| Wallet deep-dives | `wallet-profiler` | Individual wallet investigation, cross-market behavior |
| Testing & debugging | `debug-doctor` | Read logs, run tests, validate new code, trace errors |
| Simple code changes | **direct** (overseer) | Fix a bug, add a config constant, small refactors |

### Guidelines

- **Prefer direct work** for changes under ~20 lines or single-file edits.
- **Delegate** when the task is self-contained and matches an agent's specialty.
- **Chain pattern**: For complex work, run `task-decomposer` first to get a plan, then execute subtasks.
- **Data questions**: Always route to `data-analyst` — it knows the schema and has safety hooks preventing writes.
- **Post-change validation**: Always route to `debug-doctor` after modifying methods, engine, or scraper code.
- **Never** let agents modify core application logic without overseer review.

### Agent Reference

| Agent | Model | Status | Specialty |
|-------|-------|--------|-----------|
| `prompt-engineer` | opus | **Active** | Crafts/refines prompts and agent definitions |
| `search-specialist` | sonnet | **Active** | Multi-source research (codebase, web, APIs, git) |
| `task-decomposer` | sonnet | **Active** | Requirements clarification (Phase 0) + structured work breakdown with dependencies |
| `data-analyst` | opus | **Active** | SQLite queries, plotly charts, metric tracking |
| `backtest-analyst` | opus | **Active** | Interprets optimization output, method contribution analysis |
| `method-auditor` | sonnet | **Active** | Method orthogonality, implementation validation |
| `threshold-tuner` | sonnet | **Active** | Config constant sensitivity analysis |
| `api-health-checker` | haiku | Stub | Endpoint monitoring, schema validation, rate limit tracking |
| `wallet-profiler` | sonnet | Stub | Individual wallet investigation, rationality validation |
| `debug-doctor` | sonnet | **Active** | Log analysis, test execution, error tracing, bug documentation |

### Agent Activation Milestones

| Milestone | Trigger | Agent | Why |
|-----------|---------|-------|-----|
| **M1** | First full combinator run with M25-M28 | `backtest-analyst` | Interpret whether Markov methods improve fitness. **Done (Session 5).** |
| **M2** | Stable top-10 combos | `method-auditor` | Prune: which methods never appear in winners? Which are correlated? **Done (Session 7).** |
| **M3** | `method-auditor` finds threshold issues | `threshold-tuner` | Optimize constants systematically |
| **M4** | Source data APIs integrated | `api-health-checker` | Monitor 10+ endpoints before they become unmanageable |
| **M5** | Leaderboard wallet seeding implemented | `wallet-profiler` | Validate seeded wallets are genuinely sharp |
