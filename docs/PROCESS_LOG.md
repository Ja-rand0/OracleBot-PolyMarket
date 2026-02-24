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
| Bug fixes pass | Done | 34 bugs fixed (B001-B034), integrity rules established |
| Agent system deployed | Done | 7 agents + safety hook + overseer routing |
| CLAUDE.md comprehensive | Done | Full documentation with method details + bug tracking |
| config.py reconstructed | Done | Reconstructed from bytecode via `dis`/`marshal` |
| API reference documented | Done | All Polymarket endpoints + source data APIs catalogued |
| GUI roadmap defined | Done | Streamlit V1 spec with pages, color scheme |
| Method unit tests | **TODO** | Need fixtures with known outcomes |
| API caching layer | **TODO** | Market lists 5min, prices 1min, historical 1hr |
| Leaderboard wallet seeding | **TODO** | Integrate Data API `/leaderboard` for wallet discovery |
| Source data integration | **TODO** | FRED, NOAA, CoinGecko, ESPN — Phase 2 |
| Streamlit dashboard V1 | **TODO** | Migrate from rich terminal to web-based |
| Post-M3 combinator run | Done | Top combo S4+T17 at 0.3546 (+0.0472 vs baseline); T17 dominates top-10 |
| First profitable backtest | **TODO** | Requires enough resolved markets + tuned thresholds |
| Real money deployment | **TODO** | Requires consistent edge + CLOB API bet placement |

---

## Next Steps

1. ~~**Reconstruct config.py**~~ — Done (B009)
2. ~~**Deduplicate update_wallet_stats**~~ — Done (B011)
3. ~~**Post-M3 combinator run**~~ — Done (Session 9, S4+T17 at 0.3546)
4. ~~**Backfill resolved market bets**~~ — Done (Session 11, backfill loop drains 100 empty markets/cycle)
5. **Re-run combinator after backfill** — Once backtest pool grows to 100+ markets, re-run to check if 100% accuracy holds or breaks
6. **Add method unit tests** — Create fixtures with known outcomes, test each method independently
7. **Tune S1/T19 thresholds** — These weren't in the M3 top combo; re-run threshold-tuner once a combo including S1 or T19 appears in top-3
8. **Validate rationality formula** — Cross-reference with backtest accuracy to check if the 0.5/0.3/0.2 weights are meaningful
9. **Profile optimizer performance** — Time each tier, identify bottlenecks, check if Tier 3 hill-climb adds meaningful improvement
10. **Investigate method correlation** — Run pairwise signal correlation across resolved markets to identify redundant methods
11. **Integrate Data API leaderboard** — Seed wallet tracking from top profitable wallets
12. **Add caching layer** — TTL-based cache for API responses (market lists, prices, wallet data)
13. **Build Streamlit V1** — Migrate dashboard to web-based with plotly charts
14. **Integrate FRED/NOAA** — External signals for economic and weather markets

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
| B031 | 2026-02-23 | `engine/combinator.py` | tier3 hill-climb called `get_all_method_ids()` — excluded methods could re-enter via hill-climb | Build `active_method_ids` from CATEGORIES instead; removed dead import |
| B032 | 2026-02-23 | `dashboard.py` | Upsert loops inside `console.status()` spinner + missing `conn.commit()` — caused 6-hour hang on Windows (Rich thread starved SQLite timeout polling) | Moved upserts outside spinner blocks; added `conn.commit()` after each loop; added `log.info` checkpoints |
| B033 | 2026-02-23 | `statistical.py` T17 | Weight accumulator not scale-invariant — on large markets both posteriors converge to same extreme, zeroing divergence signal (B029 clamp was insufficient) | Divide weight by `n = len(bets)`; public and smart posteriors now reflect direction, not volume |
| B034 | 2026-02-23 | `emotional.py` E10/E11 | Confidence could reach 0.0 when weak signal — method contribution disappears from weighted aggregator | Added `max(0.1, ...)` floor to confidence in both methods |

---

### Session 7 — Method Pruning, Agent Expansion (2026-02-23)

**Method pruning (auditor findings applied):**
- S2 removed from active CATEGORIES: interchangeable with S1, subadditive in combos
- D6 removed from active CATEGORIES: never appears in top-25, adds graph overhead
- M25 removed from active CATEGORIES: actively hurts M26+M28 combos
- All 3 methods remain registered in METHODS (count stays 28) for future re-activation
- CATEGORIES active count: 28 → 25

**Combinator fix (B031):**
- `engine/combinator.py` tier3 hill-climb now builds `active_method_ids` from CATEGORIES
  instead of calling `get_all_method_ids()` — ensures excluded methods don't re-enter via hill-climb
- Removed dead import `from methods import get_all_method_ids`

**Agent files created:**
- `.claude/agents/debug-doctor.md` — post-change validation, log analysis, bug documentation
- `.claude/agents/backtest-analyst.md` — combo diagnosis, method contribution, fitness trend
- `method-auditor` and `threshold-tuner` promoted from Stub → Active

**Debug-doctor validation result:** WARN (no regressions; dead import flagged and resolved)

### Session 8 — M3 Threshold Tuning (2026-02-23)

**Milestone:** M3 — threshold-tuner agent activated after method-auditor (M2) completed.

**What was done:**
- Launched `threshold-tuner` agent against the top combo: D5, T17, M26, P20 (baseline fitness=0.2587)
- 60 resolved markets tested (drawn from 8037 total), 12 constants analyzed
- Agent identified 3 high-sensitivity and 2 medium-sensitivity constants; all others low/zero sensitivity

**Changes applied to config.py:**

| Constant | Old | New | Fitness Delta | Sensitivity |
|----------|-----|-----|---------------|-------------|
| `M26_TRENDING_THRESHOLD` | 0.60 | 0.33 | +0.039 to +0.047 | High |
| `T17_RATIONALITY_CUTOFF` | 0.40 | 0.58 | +0.022 to +0.023 | High |
| `P20_DEVIATION_THRESHOLD` | 0.10 | 0.02 | +0.023 | High |
| `T17_AMOUNT_NORMALIZER` | 1000.0 | 50.0 | +0.005 | Medium |
| `T17_UPDATE_STEP` | 0.10 | 0.80 | +0.004 to +0.006 | Medium |

**Combined fitness improvement (all three high-sensitivity changes):** 0.2587 → 0.3066 (+0.047914)

**Root causes:**
- M26_TRENDING_THRESHOLD=0.60 was above the Markov self-transition probability for most markets → M26 never fired, returned zero-signal. Lowering to 0.33 (near the 3-state uniform floor) activates the method.
- T17_RATIONALITY_CUTOFF=0.40 was below median wallet rationality → smart pool included average bettors, diluting the Bayesian divergence signal.
- P20_DEVIATION_THRESHOLD=0.10 required 10% VWAP deviation → too conservative; 2% threshold captures genuine but moderate Nash deviations (step function at ≤0.025).
- T17_AMOUNT_NORMALIZER=1000 made $100 bets contribute only 0.1 weight units → posterior barely moved. At 50, a $100 bet = 2.0 weight units.
- T17_UPDATE_STEP=0.10 barely moved the Bayesian posterior per bet. At 0.80, smart-wallet signals produce meaningful divergence from the public prior.

**Not changed:**
- `M26_LOW_THRESHOLD`: +0.007 alone but −0.008 when combined with M26_TRENDING_THRESHOLD change (interaction effect)
- `S1_MIN_RESOLVED_BETS`, `S1_STDDEV_THRESHOLD`, `T19_ZSCORE_THRESHOLD`: zero sensitivity (methods not in top-4 combo)
- `M26_HIGH_THRESHOLD`: zero sensitivity (HIGH state never triggered in test set)
- `M26_NUM_WINDOWS`: insensitive 5–8; values ≥10 raise FPR
- `BACKTEST_CUTOFF_FRACTION`: zero delta across 0.50–0.90 range

**Debug-doctor validation result:** PASS (T17, P20, M26 all return valid MethodResults; no import errors, no overflow, no division-by-zero; test suite DB-lock is pre-existing)

**Caveats for next session:**
- T17_AMOUNT_NORMALIZER and T17_UPDATE_STEP not tested jointly with high-sensitivity changes — run a combined test next time the combinator runs
- 0.33 trending threshold is exactly at the 3-state uniform floor — monitor FPR on M26 in the next full combinator run
- S1/T19 constants need tuning against combos that include those methods (not tested here)

### Session 9 — Post-M3 Combinator Re-Run (2026-02-23)

**What was done:**
- Full Tier1→Tier2→Tier3 combinator pass with all M3 threshold changes applied
- Tested on 25 eligible resolved markets (same set as M3 baseline)

**Results:**

| Rank | Combo | Fitness | Accuracy | Edge | FPR |
|------|-------|---------|----------|------|-----|
| 1 | S4, T17 | 0.3546 | 1.0 | 0.085 | 0.0 |
| 2 | S4, T17, D5 | ~0.34+ | 1.0 | — | 0.0 |
| 3–10 | T17-anchored combos | 0.31–0.35 | 1.0 | — | 0.0 |

- Top combo improved 0.3074 → 0.3546 (+0.0472) vs post-wipe baseline
- T17 appears in all top-10 combos — confirmed as the dominant signal anchor
- S4 (sandpit filter) pairs consistently with T17 as best preprocessor
- FPR=0.0 and Accuracy=1.0 across top-10 — consistent with small-sample regime (25 markets)
- M26 (Market Phases) drops out of the top combo after M3 tuning vs. Session 8 expectation; S4+T17 pair is tighter

**T17 signal investigation (data-analyst agent):**
- `analysis/backtest_t17_signal.py` created to inspect T17 signal direction on 25 backtest markets
- Found: T17 confidence/signal collapse on large-volume markets despite ±500 clamp (B029 band-aid insufficient)
- Root cause: `weight = amount / T17_AMOUNT_NORMALIZER` accumulates linearly with bets — on a 1000-bet market the public and smart posteriors both converge to the same extreme, zeroing the divergence
- Fix (`methods/statistical.py`): divide weight by `n = len(bets)` — makes the total update scale-invariant regardless of market size; both posteriors now reflect bet _direction_ rather than raw accumulation
- Additional analysis scripts (`backtest_q5_q7c.py`, `backtest_q7.py`, `backtest_q7b.py`, `backtest_q7d.py`) created to investigate combo Q5/Q7 performance; **uncommitted at end of session (usage limit)**

**E10/E11 confidence floor fix (`methods/emotional.py`):**
- `e10_loyalty_bias` and `e11_recency_bias` confidence could reach 0.0 when signals are weak
- Zero confidence causes these methods to contribute 0 weight in the aggregator, effectively disappearing from combos even when they fire
- Fix: `max(0.1, ...)` floor ensures minimum confidence of 0.1 — methods always contribute a small signal when they activate
- **Uncommitted at end of session (usage limit)**

**Files modified (uncommitted):**
- `methods/statistical.py` — T17 scale-invariant weight (`/ n`)
- `methods/emotional.py` — E10/E11 confidence floor (`max(0.1, ...)`)
- `analysis/backtest_t17_signal.py` — T17 signal investigation script (new)
- `analysis/backtest_q5_q7c.py`, `backtest_q7.py`, `backtest_q7b.py`, `backtest_q7d.py` — combo Q analysis scripts (new)

### Session 10 — Dashboard Hang Fix + Documentation (2026-02-23)

**Incident:** Bot found stuck overnight — oracle.bat had not collected data since 03:14:48 (6+ hours). Terminal showed "Fetching active markets..." spinner frozen.

**Diagnosis:**
- `caretaker.log`: process started at 03:14:40, never restarted (hung, not crashed)
- `bot.log`: last entry "Fetched 5000 markets total" at 03:14:48 — no DB writes after
- `polymarket.db-wal`: 0 bytes — confirmed zero writes in entire 6-hour session
- Two Python processes running (caretaker PID 49472, dashboard PID 48508) — no orphan/duplicate
- Root cause: **B032** — `dashboard.py` upsert loops ran inside `console.status()` spinner block with no `conn.commit()`; Rich's background spinner thread (Windows console API writes) competed with the main thread's first SQLite write lock acquisition, starving the 30-second timeout polling loop

**Bug B032 fix applied to `dashboard.py`:**
- Moved active-market and resolved-market upsert loops OUTSIDE their respective `console.status()` blocks (only the API fetch stays inside the spinner)
- Added `conn.commit()` after each upsert loop — the same fix that `main.py` received in B030 (commit 9c47789) was never applied to `dashboard.py`
- Added `log.info("Upserting N markets to DB...")` and `log.info("...upserts complete")` before/after each loop — future hangs can be located immediately in `bot.log`

**Session 9 uncommitted changes committed:**
- `methods/statistical.py` T17 scale-invariant weights
- `methods/emotional.py` E10/E11 confidence floors
- New analysis scripts tracked

### Session 11 — Resolved Market Backfill (2026-02-24)

**Diagnosis:**
- data-analyst investigation confirmed 2,153 of 2,211 resolved markets in DB have zero bets (97.4% empty)
- Actual backtest pool: ~28–41 markets (those that happened to be in the `fetch_resolved_markets()` API window at collection time)
- Reported 100% accuracy is statistically meaningless — based on ~35 markets, all T17-anchored
- Root cause: `collect_data()` in both `main.py` and `dashboard.py` only fetched trades for markets returned by the *current* `fetch_resolved_markets()` call; markets upserted in prior cycles with no bet data were never revisited
- T17 appears in all 50 stored method_results — selection artifact, not robust signal

**Fix applied:**
- `db.py` — added `get_resolved_markets_needing_backfill(conn, min_bets, limit)`: queries for `resolved=1` markets with fewer than `min_bets` bets, ordered by `end_date DESC` (recent first — more likely the Data API still has trade history)
- `main.py` — added `MAX_BACKFILL_FETCHES = 100` constant; added backfill pass after resolved trade fetch — drains up to 100 empty resolved markets per cycle
- `dashboard.py` — same constant and backfill pass with rich progress bar (`[magenta]Backfill trades`) and summary line

**Expected outcome:**
- At 100 markets/cycle the 2,153-market backlog drains in ~22 cycles
- Backtest pool grows from ~35 → potentially hundreds of markets
- 100% accuracy either holds (genuine signal) or breaks (small-sample artifact) — either way, the number becomes meaningful

**Files modified:**
- `data/db.py` — `get_resolved_markets_needing_backfill()`
- `main.py` — `MAX_BACKFILL_FETCHES` constant, backfill loop
- `dashboard.py` — `MAX_BACKFILL_FETCHES` constant, backfill loop with progress bar
