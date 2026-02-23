# Polymarket Bot — Development Process Log

> Updated periodically to minimize overhead. Captures key decisions, milestones, bugs, and architectural changes.

---

## Session Log

### Session 1 — Initial Build (Pre-Claude Code)

**What was built:**
- Core data pipeline: scraper.py (Gamma, Data, CLOB APIs) → db.py (SQLite) → models.py (dataclasses)
- 24 detection methods across 5 categories (S, D, E, T, P)
- 3-tier brute-force combinator (within-category → cross-category → hill-climb)
- Fitness scoring: accuracy*0.35 + edge*0.35 - FPR*0.20 - complexity*0.10
- Rich terminal dashboard with live panels, progress bars, pick display
- Caretaker watchdog for crash recovery
- Daily markdown report generation with edge-ranked picks

**Key design decisions:**
- SQLite over Postgres: single-file simplicity, no server dependency, WAL mode for concurrent reads
- 24 methods not 10: more methods = more combinations = higher chance of finding genuine edge
- Brute-force over ML: with only ~hundreds of resolved markets, ML overfits. Brute-force combo testing with fitness scoring is more honest about the data we have.
- Read-only first: build trust in the signals before risking capital

### Session 2 — Bug Fixes & Data Integrity

**Bugs found and fixed:**
- B001: NO-token odds stored incorrectly (raw price vs YES probability)
- B002: Full 140k+ wallet dict passed to methods (memory explosion)
- B003: Per-row commits causing SQLite locking under WAL mode
- B004: Tier 2 combinatorial explosion (2^N subsets)
- B005: Duplicate bets from re-fetching same trades
- B006: Method results table growing unbounded
- B007: O(n) list scan in E13 spike detection
- B008: Method function lookup repeated per market instead of per combo

**Data integrity rules established:**
- Odds normalization protocol (always store YES probability)
- Deduplication via UNIQUE indexes + INSERT OR IGNORE
- Per-market wallet filtering requirement
- Edge-over-market pick ranking (replacing raw conviction)
- Database locking prevention (timeout=30, batch commits)

### Session 3 — Claude Code Agent System (2026-02-12)

**What was built:**
- Custom agent system with 4 specialized agents:
  - `prompt-engineer` (opus) — crafts/refines prompts and agent definitions
  - `search-specialist` (sonnet) — multi-source research (codebase, web, APIs, git)
  - `task-decomposer` (sonnet) — structured work breakdown with dependency mapping
  - `data-analyst` (opus) — SQLite queries, plotly charts, metric tracking
- Safety hook (`scripts/validate_readonly_query.py`) — blocks SQL write operations from data-analyst
- Overseer routing rules in CLAUDE.md — when to delegate vs. handle directly
- Permission configuration for python, sqlite3, pip in settings.local.json
- PreToolUse hook wiring for the SQL safety validator
- Plotly installed for interactive chart generation

**What was expanded:**
- CLAUDE.md rewritten from ~94 lines to ~392 lines:
  - Full tech stack documentation with API reference
  - All config constants catalogued
  - ASCII data flow diagram
  - Complete method documentation (all 24 methods with algorithms)
  - Engine pipeline explanation (fitness, backtest, combinator, report)
  - Token efficiency rules for both Claude and user
  - Bug tracking section (8 resolved, 10 potential, 7 review areas)
  - Agent delegation rules with routing table

**Key decisions:**
- Agents stored in `.claude/agents/` (already in .gitignore — local only)
- data-analyst uses opus for complex SQL reasoning
- search-specialist and task-decomposer use sonnet (sufficient for research/planning, cheaper)
- Safety hook validates ALL Bash calls containing "sqlite3", not just agent calls

**Discoveries:**
- config.py source file is missing (P009) — only .pyc exists. High priority to reconstruct.
- update_wallet_stats is duplicated in main.py and dashboard.py (P002) — divergence risk.
- Python not on Git Bash PATH — needed full path `/c/Python314/python.exe` for pip install.

### Session 3b — config.py Reconstruction & API Integration (2026-02-12)

**config.py recovered:**
- Used `dis` + `marshal` to disassemble `.pyc` bytecode
- Every constant, line number, and variable name recovered exactly
- 126 lines: imports, logging setup, API endpoints, scraper settings, 24 method thresholds, fitness weights, combinator settings, backtest fraction
- P009 resolved → B009

**Key threshold values recovered:**
- `S1_STDDEV_THRESHOLD=2.0`, `S2_LATE_STAGE_FRACTION=0.1`, `S2_HIGH_CONVICTION_ODDS=0.85`
- `S3_TIME_WINDOW_MINUTES=10`, `S3_MIN_CLUSTER_SIZE=3`
- `E13_VOLUME_SPIKE_MULTIPLIER=3.0`, `E16_KL_THRESHOLD=1.5`
- `T18_CHI_SQUARED_PVALUE=0.05`, `T19_ZSCORE_THRESHOLD=2.5`
- `P20_DEVIATION_THRESHOLD=0.15`, `P23_ANCHOR_MIN_AMOUNT=1000.0`
- `BACKTEST_CUTOFF_FRACTION=0.75`, `SCRAPE_INTERVAL_MINUTES=15`
- Fitness weights confirmed: 0.35/0.35/0.20/0.10

**CLAUDE.md expanded with supplementary document:**
- Full Polymarket API reference: 12 additional endpoints documented (price, midpoint, spread, search, tags, events, activity, positions, leaderboard, WebSocket)
- Rate limits: Gamma 10/s, CLOB 10/s, Data 5/s, WS 5 connections
- Source data APIs catalogued: FRED (economic), NOAA/NWS (weather), CoinGecko (crypto), ESPN (sports), The Odds API (Vegas lines), GovTrack (legislation)
- Client libraries: `py-clob-client`, `polymarket-apis`
- GUI roadmap: Streamlit V1 with 7 pages, consistent color scheme
- Caching rules added: market lists 5min, prices 1min, historical 1hr
- Wallet tracking strategy: seed from leaderboard, deep-dive activity
- Source data timing: NOAA 4x/day, FRED known release dates
- 5 new potential bugs (P011-P015): caching gap, missing leaderboard integration, noisy market price, P22 O(n^2), no WebSocket
- 6 new review areas: caching layer, leaderboard seeding, WebSocket, source data, GUI migration, .env setup
- Tech stack expanded with 6 planned dependencies

### Session 4 — Quick Wins & Medium Bug Fixes (2026-02-12)

**Quick wins completed:**
- B011 (P002): Deduplicated `update_wallet_stats` — dashboard.py now imports from main.py. Fixed `datetime.now()` → `datetime.utcnow()` divergence bug.
- B013 (P005): S4 sandpit thresholds extracted to config.py — 5 new constants: `S4_SANDPIT_MIN_BETS`, `S4_SANDPIT_MAX_WIN_RATE`, `S4_SANDPIT_MIN_VOLUME`, `S4_NEW_WALLET_MAX_BETS`, `S4_NEW_WALLET_LARGE_BET`.
- B014 (P007/P008): Silent `except: pass` replaced with `log.exception()` in backtest.py (1) and dashboard.py (2).

**Medium bug fixes completed:**
- B010 (P001): Added `log.warning` in scraper.py when 30-day fallback lifespan is used for CLOB markets missing `created_at`.
- B012 (P003): T17 Bayesian weight constants extracted to config.py — `T17_AMOUNT_NORMALIZER=100`, `T17_UPDATE_STEP=0.1`, `T17_RATIONALITY_CUTOFF=0.4`.
- B015 (P010): D7 now uses its own `config.D7_MIN_BETS=10` instead of borrowing `S1_MIN_RESOLVED_BETS`.
- B016 (P013): Market price estimation in report.py now uses volume-weighted average with configurable `REPORT_PRICE_RECENT_TRADES=20` and `REPORT_PRICE_MIN_TRADES=5`.
- B017 (P014): P22 herding detection O(n^2) nested loop replaced with O(n) two-pointer sliding window.

**Files modified:**
- `config.py` — 12 new constants added (S4, D7, T17, Report)
- `dashboard.py` — duplicate function removed, import added, silent exceptions → log.exception
- `methods/suspicious.py` — S4 uses config constants
- `methods/discrete.py` — D7 uses own threshold
- `methods/statistical.py` — T17 uses config constants
- `methods/psychological.py` — P22 O(n) optimization with deque import
- `engine/backtest.py` — silent exception → log.exception
- `engine/report.py` — volume-weighted market price with config thresholds
- `data/scraper.py` — warning log for 30-day fallback

---

### Session 5 — Method Bug Fixes + Wallet Relationship Wiring (2026-02-22)

**Backtest-analyst M1 findings:**
- Only 58/3,899 resolved markets have bet data (1.5% backtest coverage)
- S4 + T17 is the dominant backbone — appears in 70-76% of top combos
- Markov methods (M25/M26/M28) appear from rank 23 onward but not top-10
- M27 (Flow Momentum) entirely absent from all tested combos
- Zero FPR across all 50 combos — suspected small-sample artifact

**Debug-doctor method diagnostic findings:**
- 6 confirmed bugs across 4 method files (D7, D8, E10, T18, P20, P22)
- 2 working methods falsely flagged as broken (T19, M27 — fire correctly)
- 2 new known issues logged (P016, P017)

**Bug fixes applied (all confirmed PASS by debug-doctor):**
- B018: D8 Boolean SAT — hardcoded `confidence=0.2` replaced with `abs(yes_ratio - 0.5) * 2` (`methods/discrete.py:219`)
- B019: T18 Benford's Law — `signal` was hardcoded `0.0`, now directional from YES/NO volume when `is_suspicious=True` (`methods/statistical.py:128`)
- B020: P20 Nash Deviation — VWAP and recent_price both now normalize NO-side odds: `(1 - b.odds)` for NO bets (`methods/psychological.py:40,45`)
- B021: P22 Herding — `expected_cluster` formula changed from `len(bets) * p_same * 0.1` to `p_same * config.P22_MIN_HERD_SIZE`; non-herding confidence changed from `0.2` to `0.0` (`methods/psychological.py:179,195`)
- B022: D7 Pigeonhole — `D7_MIN_BETS` lowered 10→3 so `sharp_count` can be non-zero on typical per-market wallet slices (`config.py:66`)
- B023: E10 Loyalty Bias — `E10_MIN_MARKETS` lowered 5→2 so wallets with 2+ bets in the market slice are evaluated (`config.py:70`)

**Wallet relationship persistence wired:**
- S3 now returns `cluster_members` in metadata (`methods/suspicious.py`)
- D6 now returns `edge_list` (top 50 edges) in metadata (`methods/discrete.py`)
- `data/db.py` — added `upsert_relationships_batch()`, removed per-row commit from `upsert_relationship()`
- New file `engine/relationships.py` — `persist_graph_relationships()` runs S3+D6 on active markets and writes to `wallet_relationships` table
- `main.py` and `dashboard.py` — call `persist_graph_relationships()` after each analysis cycle

**Files modified:**
- `config.py` — D7_MIN_BETS 10→3, E10_MIN_MARKETS 5→2
- `methods/discrete.py` — D8 confidence formula, D6 edge_list metadata
- `methods/statistical.py` — T18 directional signal
- `methods/psychological.py` — P20 VWAP normalization, P22 expected_cluster + confidence floor
- `methods/suspicious.py` — S3 cluster_members metadata
- `data/db.py` — upsert_relationships_batch()
- `engine/relationships.py` — new file
- `main.py` — persist_graph_relationships() call
- `dashboard.py` — persist_graph_relationships() call

### Session 6 — B001 Residue Fix, Data Pipeline Improvements (2026-02-22)

**Root cause confirmed (B001 residue):**
- Backtest-analyst identified that the Feb 10 edge of 10.3% was an artifact of corrupted odds data
- Five code paths were applying `(1 - b.odds)` for NO bets at read-time, double-inverting bets stored by the post-B001 scraper fix
- Only 2/25 markets had genuine edge; real max edge was ~8%
- Additionally, 11 stale method_results from Feb 10 were computed on corrupted data

**Data wipe + re-scrape:**
- Cleared 2,294,928 bets and 50 method_results from DB (markets, wallets, wallet_relationships untouched)
- Re-scraped: 5,000 active markets + 8,037 resolved markets, 238,019 clean bets across 82 markets
- New top combo post-wipe: `D5, M26, P20, T17` at fitness 0.3074 (90.1% accuracy, 2.3% edge, 0% FPR)

**Bug fixes applied:**
- B024: Removed double-inversion from `engine/backtest.py:107` — `yes_probs` no longer applies `1 - b.odds` for NO bets
- B025: Removed double-inversion from `engine/report.py:106` — VWAP market price estimation fixed
- B026: Removed double-inversion from `methods/psychological.py:40` — P20 VWAP fixed
- B027: Removed double-inversion from `methods/psychological.py:45` — P20 recent_price fixed
- B028: Simplified `methods/markov.py:68` `_normalize_odds()` — now returns `bet.odds` directly
- B029: T17 Bayesian sigmoid overflow — clamped `public_log_odds` and `smart_log_odds` to [-500, 500] before `math.exp()` (`methods/statistical.py`)
- B030: Market upserts committed per-row (5k + 8k commits/cycle) — removed `conn.commit()` from `upsert_market()`, batch commit in `main.py` after each loop

**Data pipeline improvements:**
- `data/models.py` — added `volume: float = 0.0` field to `Market` dataclass (not persisted to DB)
- `data/scraper.py` — `_parse_gamma_market()` now parses `volumeNum`/`volume` from Gamma API response
- `main.py` — active markets sorted by volume descending before `MAX_ACTIVE_TRADE_FETCHES=500` cap, ensuring highest-volume markets are always fetched first

**P016/P017 confirmed already fixed (stale entries removed from CLAUDE.md):**
- P22 dynamic cluster scaling (`same_side_total / num_windows`) was already implemented
- E10 volume-based confidence (`loyal_volume / total_volume * 2`) was already implemented

**Files modified:**
- `engine/backtest.py` — remove NO-bet inversion
- `engine/report.py` — remove NO-bet inversion in VWAP
- `methods/psychological.py` — P20 VWAP + recent_price inversion removed
- `methods/markov.py` — `_normalize_odds()` simplified
- `methods/statistical.py` — T17 sigmoid clamp
- `data/models.py` — Market.volume field
- `data/scraper.py` — parse volumeNum from Gamma API
- `data/db.py` — removed per-row commit from upsert_market
- `main.py` — volume-sort before cap + batch commits after market loops
- `claude.md` — removed stale P016/P017 known issues

---

## Architecture Decisions Record

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| ADR-001 | SQLite over Postgres | Single-file simplicity. No server. WAL mode handles concurrent reads. 787MB is within SQLite's comfort zone. | Pre-CC |
| ADR-002 | Brute-force combinator over ML | ~hundreds of resolved markets insufficient for ML. Exhaustive search + fitness scoring is more honest. | Pre-CC |
| ADR-003 | Read-only first, bet later | Build trust in signals before risking capital. Allows backtesting without consequences. | Pre-CC |
| ADR-004 | 3-tier optimization | Tier 1 (within-category) prunes the search space before Tier 2 (cross-category). Tier 3 (hill-climb) refines. Prevents 2^24 explosion. | Pre-CC |
| ADR-005 | Per-market wallet filtering | 140k+ wallets causes O(n*m) in methods. Filtering to market participants only makes methods feasible. | Session 2 |
| ADR-006 | Edge-over-market pick ranking | Raw conviction rankings pick markets where bot agrees with market (no edge). Edge ranking picks disagreements. | Session 2 |
| ADR-007 | Agent system with overseer pattern | Complex tasks benefit from specialized agents. Main session stays lean by delegating research and analysis. | Session 3 |
| ADR-008 | Safety hook for data-analyst | 787MB production database must not be accidentally modified. PreToolUse hook blocks SQL writes at the command level. | Session 3 |

---

## Metrics & Milestones

| Milestone | Status | Notes |
|-----------|--------|-------|
| Data pipeline operational | Done | Scraper collects from 3 APIs, stores in SQLite |
| 24 methods implemented | Done | All categories: S(4), D(5), E(7), T(3), P(5) |
| Combinator pipeline working | Done | Tier 1→2→3 with pruning |
| Dashboard live | Done | Rich terminal UI with picks, combos, wallet alerts |
| Caretaker watchdog | Done | Auto-restart on crash with backoff |
| Bug fixes pass | Done | 30 bugs fixed (B001-B030), integrity rules established |
| Agent system deployed | Done | 4 agents + safety hook + overseer routing |
| CLAUDE.md comprehensive | Done | Full documentation with method details + bug tracking |
| config.py reconstructed | Done | Reconstructed from bytecode via `dis`/`marshal` |
| API reference documented | Done | All Polymarket endpoints + source data APIs catalogued |
| GUI roadmap defined | Done | Streamlit V1 spec with pages, color scheme |
| Method unit tests | **TODO** | Need fixtures with known outcomes |
| API caching layer | **TODO** | Market lists 5min, prices 1min, historical 1hr |
| Leaderboard wallet seeding | **TODO** | Integrate Data API `/leaderboard` for wallet discovery |
| Source data integration | **TODO** | FRED, NOAA, CoinGecko, ESPN — Phase 2 |
| Streamlit dashboard V1 | **TODO** | Migrate from rich terminal to web-based |
| First profitable backtest | **TODO** | Requires enough resolved markets + tuned thresholds |
| Real money deployment | **TODO** | Requires consistent edge + CLOB API bet placement |

---

## Next Steps

1. ~~**Reconstruct config.py**~~ — Done (B009)
2. ~~**Deduplicate update_wallet_stats**~~ — Done (B011)
3. **Add method unit tests** — Create fixtures with known outcomes, test each method independently
4. **Validate rationality formula** — Cross-reference with backtest accuracy to check if the 0.5/0.3/0.2 weights are meaningful
5. **Profile optimizer performance** — Time each tier, identify bottlenecks, check if Tier 3 hill-climb adds meaningful improvement
6. **Investigate method correlation** — Run pairwise signal correlation across resolved markets to identify redundant methods
7. **Integrate Data API leaderboard** — Seed wallet tracking from top profitable wallets
8. **Add caching layer** — TTL-based cache for API responses (market lists, prices, wallet data)
9. **Build Streamlit V1** — Migrate dashboard to web-based with plotly charts
10. **Integrate FRED/NOAA** — External signals for economic and weather markets

---

## Resolved Bugs

| ID | Date | Module | Description | Fix |
|----|------|--------|-------------|-----|
| B001 | — | `scraper.py` | NO-token odds stored as raw price instead of YES probability | `_parse_trade()` now stores `1 - price` for NO tokens |
| B002 | — | `backtest.py` | Full wallet dict (140k+) passed to every method call | Added per-market wallet filtering |
| B003 | — | `db.py` | Per-row commits in `insert_method_result` causing DB locks | Removed per-row commit; use `flush_method_results()` |
| B004 | — | `combinator.py` | Tier 2 tried all 2^N subsets causing combinatorial explosion | Changed to pairs/triples of finalists only |
| B005 | — | `bets` table | Duplicate bets from re-fetching same trades | Added UNIQUE index + `INSERT OR IGNORE` dedup |
| B006 | — | `method_results` | Unbounded table growth from optimizer runs | Added `prune_method_results(keep=50)` |
| B007 | — | `emotional.py` E13 | O(n) list scan for spike bet membership | Changed to `set` for O(1) lookup |
| B008 | — | `backtest.py` | Method function re-lookup on every market iteration | Cached `method_fns` once per combo |
| B009 | 2026-02-12 | `config.py` | Source file missing — only `.pyc` existed | Reconstructed from bytecode disassembly via `dis`/`marshal` |
| B010 | — | `scraper.py` | Silent 30-day fallback with no visibility | Added `log.warning` when fallback is used |
| B011 | — | `main.py`/`dashboard.py` | Duplicate update_wallet_stats + `datetime.now()` vs `utcnow()` divergence | Deduplicated; fixed to `utcnow()` throughout |
| B012 | — | `statistical.py` T17 | Bayesian weight constants hardcoded | Extracted to config.py: `T17_AMOUNT_NORMALIZER`, `T17_UPDATE_STEP`, `T17_RATIONALITY_CUTOFF` |
| B013 | — | `suspicious.py` S4 | Sandpit thresholds hardcoded | Extracted to config.py: `S4_SANDPIT_MIN_BETS`, `S4_SANDPIT_MAX_WIN_RATE`, `S4_SANDPIT_MIN_VOLUME`, `S4_NEW_WALLET_MAX_BETS`, `S4_NEW_WALLET_LARGE_BET` |
| B014 | — | `backtest.py`/`dashboard.py` | Silent exceptions swallowing errors | Replaced bare `except` with `log.exception()` |
| B015 | — | `discrete.py` D7 | D7 used `S1_MIN_RESOLVED_BETS` instead of its own threshold | Added `D7_MIN_BETS` to config.py |
| B016 | — | `report.py` | Market price used simple average instead of VWAP | Now uses volume-weighted average with `REPORT_PRICE_RECENT_TRADES` and `REPORT_PRICE_MIN_TRADES` |
| B017 | — | `psychological.py` P22 | O(n^2) sliding window for herding detection | Replaced with O(n) two-pointer approach |
| B018 | 2026-02-22 | `discrete.py` D8 | Hardcoded `confidence=0.2` | Replaced with `abs(yes_ratio - 0.5) * 2` |
| B019 | 2026-02-22 | `statistical.py` T18 | Signal hardcoded `0.0` regardless of suspicious result | Now directional from YES/NO volume when `is_suspicious=True` |
| B020 | 2026-02-22 | `psychological.py` P20 | VWAP/recent_price not normalizing NO-side odds | Added `(1 - b.odds)` for NO bets (later superseded by B026/B027) |
| B021 | 2026-02-22 | `psychological.py` P22 | `expected_cluster` formula wrong; non-herding confidence was 0.2 | Fixed formula; non-herding confidence set to 0.0 |
| B022 | 2026-02-22 | `config.py` D7 | `D7_MIN_BETS` too high (10) — sharp_count always 0 | Lowered to 3 |
| B023 | 2026-02-22 | `config.py` E10 | `E10_MIN_MARKETS` too high (5) — most wallets skipped | Lowered to 2 |
| B024 | 2026-02-22 | `backtest.py` | Double-inversion: `1 - b.odds` applied to post-B001 NO bets | Removed inversion — `b.odds` always stores YES probability |
| B025 | 2026-02-22 | `report.py` | Double-inversion in VWAP market price estimation | Removed inversion |
| B026 | 2026-02-22 | `psychological.py` P20 | Double-inversion in P20 VWAP (introduced by B020) | Removed inversion |
| B027 | 2026-02-22 | `psychological.py` P20 | Double-inversion in P20 recent_price | Removed inversion |
| B028 | 2026-02-22 | `markov.py` | `_normalize_odds()` inverting post-B001 NO odds | Simplified to `return bet.odds` |
| B029 | 2026-02-22 | `statistical.py` T17 | `math.exp()` overflow on high-volume markets | Clamp log-odds to [-500, 500] before sigmoid |
| B030 | 2026-02-22 | `db.py` / `main.py` | `upsert_market()` committed per-row (13k+ commits/cycle) | Removed commit from function; batch after loop in main.py |
