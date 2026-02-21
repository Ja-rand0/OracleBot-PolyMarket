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
| Bug fixes pass | Done | 17 bugs fixed (B001-B017), integrity rules established |
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
