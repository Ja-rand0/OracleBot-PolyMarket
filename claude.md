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
| Econ Data | `fredapi` | FRED economic series for rate/inflation markets (planned) |
| Weather | `noaa-sdk` | NWS forecasts for weather markets (planned) |
| Crypto | `pycoingecko` | CoinGecko price/volume data for crypto markets (planned) |
| Platform | Windows 10, Git Bash sandbox | Dev environment |

### API Dependencies

| API | Base URL | Auth | Pagination | Purpose |
|-----|----------|------|------------|---------|
| **Gamma** | `gamma-api.polymarket.com/markets` | None | Offset (`offset`, `limit`) | Market discovery (richest metadata) |
| **Data** | `data-api.polymarket.com/trades` | None | Offset (hard cap ~3500) | Public trade history |
| **CLOB** | `clob.polymarket.com` | None (read) | Cursor (`next_cursor`, `MA==` start, `LTE=` end) | Orderbook, pricing, resolved outcomes |
| **Polygonscan** | `api.polygonscan.com/api` | API key | Page-based | On-chain wallet transactions (optional) |

**Polymarket data hierarchy:** Event → Market(s) → Outcome Token(s). An Event is a question (e.g. "Fed rate cuts in 2025?"), a Market is a specific option, each Market has YES/NO tokens with prices summing to ~$1.00. Always resolve down to `token_id` for price/orderbook queries.

#### Additional Polymarket Endpoints (not yet integrated)

| Endpoint | URL Pattern | Purpose |
|----------|------------|---------|
| Price | `CLOB/price?token_id=X&side=BUY` | Current token price |
| Midpoint | `CLOB/midpoint?token_id=X` | Mid price between bid/ask |
| Spread | `CLOB/spread?token_id=X` | Bid-ask spread |
| Tick Size | `CLOB/tick-size?token_id=X` | Minimum price increment |
| Last Trade | `CLOB/last-trade-price?token_id=X` | Most recent execution price |
| Gamma Search | `Gamma/search?query=X` | Full-text market/event search |
| Gamma Tags | `Gamma/tags` | Category list (Politics, Sports, Crypto, etc.) |
| Gamma Events | `Gamma/events` | Event-level data with nested markets |
| Data Activity | `Data/activity?address=X` | Wallet trade history (critical for wallet tracking) |
| Data Positions | `Data/positions?address=X` | Current open positions |
| Data Leaderboard | `Data/leaderboard?window=7d` | Top wallets by profit/volume |
| WebSocket | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | Real-time price/orderbook updates |

#### Polymarket Client Libraries

- `py-clob-client` — Official CLOB client. Read-only: `ClobClient("https://clob.polymarket.com")` with no private key.
- `polymarket-apis` — Unified wrapper for Gamma + CLOB + Data + WebSocket + GraphQL.

#### API Rate Limits (approximate, not officially published)

| Service | Rate | Notes |
|---------|------|-------|
| Gamma API | ~10 req/s | Generous. Cache market lists for 5 min. |
| CLOB (public) | ~10 req/s | Higher for authenticated. Cache prices for 1 min. |
| Data API | ~5 req/s | Paginate carefully. Cache wallet data for 5 min. |
| WebSocket | 5 connections | Reconnect with exponential backoff + jitter. |

#### Source Data APIs (planned — for enriching market analysis)

| API | Purpose | Auth | Key Series/Endpoints |
|-----|---------|------|---------------------|
| **FRED** (`fredapi`) | Economic data for rate/inflation markets | Free API key | `FEDFUNDS`, `CPIAUCSL`, `UNRATE`, `PAYEMS`, `DGS10`, `T10Y2Y`, `UMCSENT` |
| **NOAA/NWS** (`api.weather.gov`) | Weather data for weather markets | None (set User-Agent) | `/points/{lat},{lon}` → `/forecast`, `/alerts/active?area={state}` |
| **NCEI** (`ncei.noaa.gov`) | Historical weather for backtesting | Free token | `daily-summaries`: TMAX, TMIN, PRCP, SNOW, AWND |
| **CoinGecko** (`pycoingecko`) | Crypto data for crypto markets | Free (30 req/min) | `/simple/price`, `/coins/{id}/market_chart`, Fear & Greed index |
| **ESPN** (unofficial) | Sports scores/injuries for sports markets | None | `/apis/site/v2/sports/{sport}/{league}/scoreboard` |
| **The Odds API** | Vegas lines comparison | Free (500 req/mo) | `/v4/sports/{sport}/odds` — multiple bookmaker odds |
| **GovTrack** (`govtrack.us/api`) | Bill tracking for policy markets | None | `/api/v2/bill/{id}` — legislation progress |

**Implementation timing:** Source data APIs are Phase 2. Current phase focuses on Polymarket-native data only. Source APIs add external signals that can validate or conflict with market-derived signals.

### Config Constants (referenced across codebase, defined in config.py)

**API**: `API_MAX_RETRIES`, `API_RETRY_BACKOFF`, `API_REQUEST_TIMEOUT`, `GAMMA_MARKETS_ENDPOINT`, `POLYMARKET_MARKETS_ENDPOINT`, `POLYMARKET_BASE_URL`, `POLYGONSCAN_API_KEY`, `POLYGONSCAN_BASE_URL`

**Engine**: `FITNESS_W_ACCURACY=0.35`, `FITNESS_W_EDGE=0.35`, `FITNESS_W_FALSE_POS=0.20`, `FITNESS_W_COMPLEXITY=0.10`, `BACKTEST_CUTOFF_FRACTION`, `TIER1_TOP_PER_CATEGORY`, `TIER2_TOP_OVERALL`, `SCRAPE_INTERVAL_MINUTES`, `DB_PATH`

**Method thresholds**: `S1_MIN_RESOLVED_BETS`, `S1_STDDEV_THRESHOLD`, `S2_LATE_STAGE_FRACTION`, `S2_HIGH_CONVICTION_ODDS`, `S3_TIME_WINDOW_MINUTES`, `S3_MIN_CLUSTER_SIZE`, `E10_MIN_MARKETS`, `E10_CONSISTENCY_THRESHOLD`, `E12_WINDOW_HOURS`, `E13_VOLUME_SPIKE_MULTIPLIER`, `E14_LOW_CORRELATION_THRESHOLD`, `E15_ROUND_DIVISOR`, `E16_KL_THRESHOLD`, `T18_CHI_SQUARED_PVALUE`, `T19_ZSCORE_THRESHOLD`, `P20_DEVIATION_THRESHOLD`, `P21_LOW_PROB`, `P21_HIGH_PROB`, `P22_MIN_HERD_SIZE`, `P22_TIME_WINDOW_MINUTES`, `P23_ANCHOR_MIN_AMOUNT`, `P24_HIGH_RATIO`, `P24_LOW_RATIO`, `M25_MIN_WALLET_BETS`, `M25_SMALL_MULTIPLIER`, `M25_LARGE_MULTIPLIER`, `M25_ESCALATION_THRESHOLD`, `M25_CONFIDENCE_CAP`, `M26_NUM_WINDOWS`, `M26_LOW_THRESHOLD`, `M26_HIGH_THRESHOLD`, `M26_TRENDING_THRESHOLD`, `M27_NUM_WINDOWS`, `M27_FLOW_THRESHOLD`, `M27_MOMENTUM_THRESHOLD`, `M28_SMART_THRESHOLD`, `M28_RETAIL_THRESHOLD`, `M28_NUM_WINDOWS`, `M28_MIN_SMART_WALLETS`, `M28_MIN_RETAIL_WALLETS`, `TOTAL_METHODS`

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
  PROCESS_LOG.md         — development journal (updated periodically)
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

### Category S — Suspicious Wallet Detection (S1-S4)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **S1** | Win Rate Outlier | Wallets with statistically abnormal win rates | Flag wallets with win rate > mean + `S1_STDDEV_THRESHOLD` * stddev. Requires `S1_MIN_RESOLVED_BETS` minimum. Signal = YES/NO volume ratio of sharp wallets. Confidence scales with number of sharp wallets (cap at 10). |
| **S2** | Bet Timing | Late-stage high-conviction bets suggesting insider knowledge | Identifies bets in the final `S2_LATE_STAGE_FRACTION` of market lifespan where odds are extreme (≥ `S2_HIGH_CONVICTION_ODDS`). Signal = direction of late money. Confidence scales with count (cap at 5). |
| **S3** | Coordination Clustering | Coordinated wallet groups betting together | Builds co-occurrence graph: wallets betting same side within `S3_TIME_WINDOW_MINUTES` window. Requires ≥2 co-occurrences per edge. Runs Louvain community detection. Flags clusters ≥ `S3_MIN_CLUSTER_SIZE`. Min 10 bets to skip expensive graph ops. **Deps**: networkx, python-louvain. |
| **S4** | Sandpit Filter | Bait/trap accounts that distort the signal | Three patterns: (1) flagged_sandpit wallets, (2) ≥10 bets + <25% win rate + >$5000 volume (consistent losers), (3) ≤3 total bets + any single bet >$2000 (suspiciously large first bet). Returns cleaned bet list. |

### Category D — Discrete Math Methods (D5-D9)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **D5** | Vacuous Truth | Markets where structure makes one outcome near-certain | Checks median odds: if ≥0.95 → YES certain, if ≤0.05 → NO certain. Confidence = distance from 0.90/0.10 boundary. This filters out markets that are already settled. |
| **D6** | PageRank | Influential wallets in the copy-trading graph | Builds directed temporal graph: wallet A → wallet B if B bets the same side within 10 minutes after A. Runs PageRank. Signal = PageRank-weighted YES/NO volume. Confidence scales with node count (cap at 20). Min 10 bets. **Deps**: networkx. |
| **D7** | Pigeonhole Noise | Too many "sharp" wallets (most are just lucky) | Estimates max plausible insiders as sqrt(active_wallets). If actual sharp count exceeds this, applies noise discount. Signal = raw volume signal * (1 - noise_ratio). Uses `S1_MIN_RESOLVED_BETS` threshold. |
| **D8** | Boolean SAT | Structural bet distribution skew | If ≥80% of bets favor one side, the structure itself is skewed. Linear signal mapping for balanced markets. Simple bet count ratio analysis. |
| **D9** | Set Partition | Clean vs. emotional bet separation | Partitions bets by wallet rationality_score (<0.4 = emotional). Signal from clean bets only. Higher emotion_ratio = market is more exploitable = higher confidence. Master filter method. |

### Category E — Emotional Bias Filters (E10-E16)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **E10** | Loyalty Bias | Wallets that always bet the same side | Flags wallets with ≥`E10_MIN_MARKETS` bets where ≥`E10_CONSISTENCY_THRESHOLD` are on one side. Removes from signal. |
| **E11** | Recency Bias | Early bets extrapolating from recent events | Compares first-20% bet ratio to remaining-80%. If skew >0.3, filters wallets that only bet early (and didn't return later with information). |
| **E12** | Revenge Betting | Tilt/chase behavior after losses | Detects bet size increasing ≥1.5x within `E12_WINDOW_HOURS` hours, with current bet >$100. These are emotional doublings-down. |
| **E13** | Hype Detection | Volume spikes from media/social attention | Buckets bets hourly. Flags hours where volume ≥ `E13_VOLUME_SPIKE_MULTIPLIER` * median hourly volume. Removes spike-window bets. Uses `set` membership for O(1) filtering. |
| **E14** | Odds Sensitivity | Bettors who don't adjust size with odds | Computes correlation between bet amount and odds per wallet. Low correlation (< `E14_LOW_CORRELATION_THRESHOLD`) = emotional (flat betting regardless of edge). |
| **E15** | Round Numbers | Emotional bets at round amounts ($50, $100, $500) | Flags wallets where >70% of bets are divisible by `E15_ROUND_DIVISOR`. Sharp money uses precise sizing. |
| **E16** | KL Divergence | Wallets with extreme YES/NO skew | Computes KL divergence of each wallet's YES/NO ratio from uniform (0.5, 0.5). Wallets above `E16_KL_THRESHOLD` are biased. |

### Category T — Statistical Analysis (T17-T19)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **T17** | Bayesian Updating | Smart vs. public opinion divergence | Computes two posteriors from the same prior: (1) public (all bets), (2) smart (only rationality ≥0.4 wallets, weighted by rationality). Signal = divergence * 5, confidence = divergence * 3. **Deps**: scipy. |
| **T18** | Benford's Law | Manufactured/coordinated bet amounts | Extracts leading digits of bet amounts, tests against Benford's distribution via chi-squared (df=8). p-value < `T18_CHI_SQUARED_PVALUE` = suspicious. Non-directional signal (flags the market, not a side). Min 20 bets. **Deps**: scipy. |
| **T19** | Z-Score Outlier | Statistically unusual bet sizes | Flags bets with z-score > `T19_ZSCORE_THRESHOLD`. Cross-references with wallet rationality: high-rationality outliers = sharp money signal, low-rationality = noise. |

### Category P — Psychological / Sociological Signals (P20-P24)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **P20** | Nash Deviation | Information asymmetry via price divergence | Compares VWAP (equilibrium proxy) to last-10-bet average price. Deviation > `P20_DEVIATION_THRESHOLD` suggests informed trading is pushing the marginal price away from equilibrium. |
| **P21** | Prospect Theory | Kahneman/Tversky probability weighting mispricing | Applies the probability weighting function (gamma=0.61): low-probability events are over-bet (signal NO), high-probability events are under-bet (signal YES). Thresholds: `P21_LOW_PROB`, `P21_HIGH_PROB`. |
| **P22** | Herding | Temporal clustering of same-side bets | Sliding window detects max same-side cluster. Compares to expected cluster under random betting. If herding detected (independence_score <0.5), discounts signal by 50%. Min `P22_MIN_HERD_SIZE` bets. |
| **P23** | Anchoring | Market stuck on the first large bet's price | Finds anchor = first bet ≥ `P23_ANCHOR_MIN_AMOUNT`. Measures how much subsequent bets cluster around anchor odds (mean absolute diff). If anchoring_strength >0.7, signal = direction of late money (which may disagree with the anchor). |
| **P24** | Wisdom vs Madness | Market efficiency estimator | Meta-signal: measures what % of bets are emotional (rationality <0.4). High ratio (> `P24_HIGH_RATIO`) = "madness of crowds" → market is exploitable, trust signal. Low ratio (< `P24_LOW_RATIO`) = "wisdom of crowds" → market is efficient, dampen signal. |

### Category M — Markov Chain / Temporal Transition Analysis (M25-M28)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **M25** | Wallet Regime | Wallets escalating bet sizes (informed accumulation) | Groups bets by wallet, classifies each into size tier (small/medium/large relative to wallet median). Builds 3x3 transition matrix per wallet. Escalation score = `(P(S→M) + P(M→L) + P(S→L)) / 3`. Flags wallets above `M25_ESCALATION_THRESHOLD`. Signal = YES/NO volume ratio of escalating wallets. |
| **M26** | Market Phases | Trending vs. mean-reverting market price dynamics | Divides timeline into `M26_NUM_WINDOWS` windows. Classifies each by median YES-prob: LOW/MID/HIGH. Builds transition matrix. Trending score = average self-transition probability. If > `M26_TRENDING_THRESHOLD`, signal = direction of last state. |
| **M27** | Flow Momentum | Persistent directional bet flow vs. oscillation | Divides into `M27_NUM_WINDOWS` windows. Net dollar flow per window → YES_HEAVY/BALANCED/NO_HEAVY. Momentum score = `(P(Y→Y) + P(N→N)) / 2`. High momentum = signal follows flow. High reversal = contrarian signal. |
| **M28** | Smart-Follow | Smart money leading retail in temporal betting order | Splits wallets by rationality into smart (≥`M28_SMART_THRESHOLD`) and retail (<`M28_RETAIL_THRESHOLD`). Per time window: who bets first? Builds SMART_LEADS/MIXED/RETAIL_LEADS transition matrix. If smart leads persistently, signal = smart money direction. Contrarian amplification when retail leads opposite. |

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

**Current:** Rich terminal dashboard (`dashboard.py`) — live panels, progress bars, pick display, combo tables.

**V1 (planned):** Streamlit web dashboard. Faster to prototype, sufficient for analysis.

| Page | Content |
|------|---------|
| Dashboard | Top exploitable markets, suspicious activity feed, DB stats, best combo |
| Markets | Filterable market table with edge, madness ratio, signal. Drill into individual market analysis. |
| Wallets | Wallet search, profile cards (win rate, volume, rationality, flags), trade history |
| Method Performance | Per-method accuracy/edge across resolved markets, correlation matrix between methods |
| Combo Results | Top 50 combos table, fitness breakdown, add/remove method impact |
| Reports | Historical daily reports, pick accuracy tracking over time |
| Settings | Scan interval, thresholds, API keys, cost parameters |

**Color scheme** (consistent across all visualizations):
- Bullish/YES: `#22c55e` (green), Bearish/NO: `#ef4444` (red), Neutral: `#6b7280` (gray)
- Emotional bets: `#f59e0b` (amber), Rational bets: `#3b82f6` (blue), Suspicious: `#a855f7` (purple), Sandpit: `#dc2626` (dark red)
- Method categories: S=`#a855f7`, D=`#3b82f6`, E=`#f59e0b`, T=`#22c55e`, P=`#ec4899`, M=`#06b6d4`

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
- **Cache aggressively.** Market lists: 5 min. Prices: 1 min. Historical data: 1 hour. Wallet profiles: 5 min. API data doesn't change every second.
- **Wallet tracking strategy.** Seed from Data API leaderboard (top profitable wallets). Deep-dive their `/activity` history. Track wallets that consistently appear in sharp-money methods.
- **Source data timing.** NOAA updates forecasts 4x/day. FRED has known release dates (BLS = first Friday, CPI = ~10th). Pre-schedule pulls for maximum edge on related markets.

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

Claude Code operates on tokens. Every file read, tool call, and response consumes tokens. Follow these rules to minimize waste:

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

### Resolved Bugs

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

### Known Issues / Potential Bugs

| ID | Module | Risk | Description |
|----|--------|------|-------------|
| P001 | `scraper.py` | ~~Medium~~ **Resolved** | Added log.warning when 30-day fallback is used — visibility into which markets are affected (B010). |
| P002 | `main.py` / `dashboard.py` | ~~Low~~ **Resolved** | Deduplicated: dashboard.py now imports from main.py. Also fixed datetime.now() → utcnow() divergence (B011). |
| P003 | `statistical.py` T17 | ~~Medium~~ **Resolved** | Bayesian weight constants extracted to config.py: T17_AMOUNT_NORMALIZER, T17_UPDATE_STEP, T17_RATIONALITY_CUTOFF (B012). |
| P004 | `psychological.py` P21 | Low | Prospect theory weighting function `(pg + (1-p)^gamma)^(1/gamma)` may not match original Tversky-Kahneman formula exactly |
| P005 | `suspicious.py` S4 | ~~Medium~~ **Resolved** | Sandpit thresholds extracted to config.py: S4_SANDPIT_MIN_BETS, S4_SANDPIT_MAX_WIN_RATE, S4_SANDPIT_MIN_VOLUME, S4_NEW_WALLET_MAX_BETS, S4_NEW_WALLET_LARGE_BET (B013). |
| P006 | `report.py` | Low | `Wallet(address="")` placeholder created for missing wallets in emotion ratio calc — could cause issues if Wallet fields are accessed |
| P007 | `backtest.py` | ~~Medium~~ **Resolved** | Silent exceptions replaced with log.exception() in backtest.py and dashboard.py (B014). |
| P008 | `dashboard.py` | ~~Low~~ **Resolved** | Trade fetch failures now logged via log.exception() (B014). |
| P009 | `config.py` | ~~High~~ **Resolved** | Source file reconstructed from .pyc bytecode (B009). |
| P010 | `discrete.py` D7 | ~~Low~~ **Resolved** | D7 now uses its own config.D7_MIN_BETS instead of S1_MIN_RESOLVED_BETS (B015). |
| P011 | `scraper.py` | Medium | No caching layer — repeated API calls for same data within a cycle waste rate limit budget |
| P012 | `scraper.py` | Low | `fetch_trades_for_market` uses Data API but leaderboard/activity endpoints not integrated — missing wallet seeding |
| P013 | `report.py` | ~~Medium~~ **Resolved** | Market price now uses volume-weighted average with configurable REPORT_PRICE_RECENT_TRADES and REPORT_PRICE_MIN_TRADES (B016). |
| P014 | `psychological.py` P22 | ~~Medium~~ **Resolved** | O(n^2) sliding window replaced with O(n) two-pointer approach (B017). |
| P015 | `scraper.py` | Low | WebSocket not implemented — only REST polling. Real-time data would improve detection latency |

### Areas Needing Review

| Area | Priority | Notes |
|------|----------|-------|
| `config.py` reconstruction | ~~High~~ **Done** | Reconstructed from bytecode. See B009. |
| Wallet rationality formula | Medium | `win_rate * 0.5 + (1 - round_ratio) * 0.3 + 0.2` — weights are arbitrary. Needs validation against backtest data. |
| Method independence | Medium | Some methods may be highly correlated (e.g., E10 loyalty + E16 KL divergence). Correlated methods in a combo don't add information but increase complexity penalty. |
| Edge calculation precision | Medium | `bot_prob = 0.5 + signal * 0.5` is a linear mapping. May not accurately represent probability when multiple methods disagree. |
| Data API offset cap | Low | Hard cap at ~3500 offset means markets with >3500 trades have incomplete data. May bias toward smaller markets. |
| S3/D6 graph scalability | Low | O(n^2) edge building. Cap at 500 bets helps but very active markets may still be slow. Consider time-window pruning. |
| Test coverage | Medium | `test_pipeline.py` exists but unclear scope. Methods need unit tests with known-outcome fixtures. |
| API caching layer | Medium | No caching between cycles. Market lists, prices, wallet data should be cached with TTLs to reduce API load. |
| Leaderboard wallet seeding | Medium | Data API `/leaderboard` not used. Should seed wallet tracking from consistently profitable wallets. |
| WebSocket integration | Low | All data collection is REST-based polling. WebSocket would enable real-time spike detection (E13) and faster S2 timing signals. |
| Source data integration | Low | FRED, NOAA, CoinGecko, ESPN not yet integrated. These provide external validation signals for market-specific categories. |
| GUI migration | Low | Terminal dashboard works but limits access. Streamlit V1 would enable remote monitoring and richer visualizations. |
| `.env` for secrets | Medium | `POLYGONSCAN_API_KEY` read from env but no `.env` file or `python-dotenv` setup. Future source API keys need structured config. |

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

The main Claude Code session acts as an **overseer** that delegates to specialized subagents for self-contained tasks.

### Routing Table

| Task Type | Agent | Examples |
|-----------|-------|---------|
| Prompt writing/refinement | `prompt-engineer` | Write agent system prompts, improve method descriptions, craft LLM-facing text |
| Research & information gathering | `search-specialist` | Find API rate limits, trace data flow, investigate git history, look up library docs |
| Complex task planning | `task-decomposer` | Plan new method implementation, design schema migration, scope a refactor |
| Data analysis & visualization | `data-analyst` | Query bet distributions, chart wallet activity, compute method performance metrics |
| Backtest interpretation | `backtest-analyst` | Interpret optimization results, identify method contributions, diagnose combo performance |
| Method quality review | `method-auditor` | Check method orthogonality, validate implementations, flag dead-weight methods |
| Threshold optimization | `threshold-tuner` | Analyze sensitivity of config constants, propose adjustments based on backtest data |
| API reliability | `api-health-checker` | Ping endpoints, validate schemas, monitor rate limits, flag stale data |
| Wallet deep-dives | `wallet-profiler` | Investigate individual wallet histories, cross-market behavior, rationality validation |
| Testing & debugging | `debug-doctor` | Read logs, run tests, validate new code, trace errors, document bugs |
| Simple code changes | **direct** (overseer) | Fix a bug, add a config constant, small refactors |

### Guidelines

- **Prefer direct work** for changes under ~20 lines or single-file edits.
- **Delegate** when the task is self-contained and matches an agent's specialty.
- **Chain pattern**: For complex work, run `task-decomposer` first to get a plan, then execute subtasks (directly or via other agents).
- **Data questions**: Always route to `data-analyst` — it knows the schema and has safety hooks preventing writes.
- **Post-change validation**: Always route to `debug-doctor` after modifying methods, engine, or scraper code. It reads logs, reports, and runs tests.
- **Never** let agents modify core application logic without overseer review.

### Agent Reference

| Agent | Model | Status | Specialty |
|-------|-------|--------|-----------|
| `prompt-engineer` | opus | **Active** | Crafts/refines prompts and agent definitions |
| `search-specialist` | sonnet | **Active** | Multi-source research (codebase, web, APIs, git) |
| `task-decomposer` | sonnet | **Active** | Structured work breakdown with dependencies |
| `data-analyst` | opus | **Active** | SQLite queries, plotly charts, metric tracking |
| `backtest-analyst` | opus | **Active** | Interprets optimization output, method contribution analysis, combo diagnostics |
| `method-auditor` | sonnet | Stub | Method orthogonality, implementation validation, dead-weight detection |
| `threshold-tuner` | sonnet | Stub | Config constant sensitivity analysis, parameter optimization proposals |
| `api-health-checker` | haiku | Stub | Endpoint monitoring, schema validation, rate limit tracking, data freshness |
| `wallet-profiler` | sonnet | Stub | Individual wallet investigation, cross-market behavior, rationality validation |
| `debug-doctor` | sonnet | **Active** | Log analysis, test execution, error tracing, regression detection, bug documentation |

### Agent Activation Milestones

| Milestone | Trigger | Agent to Activate | Why |
|-----------|---------|-------------------|-----|
| **M1** | First full combinator run with M25-M28 | `backtest-analyst` | Need to interpret whether Markov methods improve fitness. **Ready now.** |
| **M2** | Combinator consistently produces stable top-10 combos | `method-auditor` | Time to prune: which methods never appear in winners? Which are correlated? |
| **M3** | `method-auditor` identifies threshold sensitivity issues | `threshold-tuner` | Audit reveals which constants matter most — tuner optimizes them systematically |
| **M4** | Source data APIs integrated (FRED, NOAA, CoinGecko, ESPN) | `api-health-checker` | Going from 4 to 10+ endpoints — need automated monitoring before it becomes unmanageable |
| **M5** | Leaderboard wallet seeding implemented (P012) | `wallet-profiler` | Deep-diving seeded wallets to validate they're genuinely sharp, not just lucky |

### Backtest Analyst — Full Specification

**Model:** opus (needs reasoning for nuanced interpretation)

**Purpose:** Interprets combinator optimization results to answer: what's working, what's not, and what to change next. This is the feedback loop between "run the optimizer" and "make the bot better."

**Capabilities:**
1. **Combo diagnosis** — Given a combo's fitness breakdown (accuracy, edge, FPR, complexity), explain why it scores the way it does. Identify which methods contribute signal vs. which add noise.
2. **Method contribution** — Across all tested combos, rank methods by how often they appear in top-N results. Flag methods that never appear (candidates for removal or threshold adjustment).
3. **Category synergy** — Identify which cross-category pairings produce the best Tier 2 results. E.g., "S+M combos consistently outperform S+E combos."
4. **Fitness trend** — Compare current optimization run to previous runs. Is fitness improving? Plateauing? Degrading?
5. **Edge analysis** — For top picks, break down where the edge comes from: is it the bot disagreeing with the market, or is it high confidence on an already-likely outcome?
6. **False positive diagnosis** — When FPR is high, trace which methods are producing the false signals and on which market types.

**Data access:** Read-only SQLite queries on `method_results`, `markets`, `bets`, `wallets` tables. Same safety hook as `data-analyst` (`scripts/validate_readonly_query.py`).

**Input format:** Overseer provides context like "analyze the latest optimization run" or "compare M-category methods against the baseline."

**Output format:** Structured markdown with:
- Summary (2-3 key findings)
- Tables (method rankings, combo breakdowns)
- Recommendations (specific next steps: adjust threshold X, drop method Y, investigate market type Z)

**Example queries:**
- "Analyze the top 10 combos from the latest run — do any M methods appear?"
- "Which methods have the highest marginal fitness contribution?"
- "Why does combo [S1,E13,M27] have high accuracy but negative edge?"
- "Compare fitness distribution before and after adding Markov methods"

### Debug Doctor — Full Specification

**Model:** sonnet (fast enough for log parsing, smart enough for root cause analysis)

**Purpose:** The testing, debugging, and documentation agent. Reads all output the bot produces — logs, reports, test results — and maintains a clear picture of system health. After any code change (like adding M25-M28), this agent validates the integration, catches regressions, and documents issues.

**Data sources (read-only):**
1. `bot.log` — Main runtime log. Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s` (ISO 8601 UTC). Contains INFO, WARNING, ERROR, and EXCEPTION entries with full stack traces.
2. `caretaker.log` — Watchdog process log. Format: `%(asctime)s [CARETAKER] %(message)s`. Tracks dashboard launches, crashes, restart counts, exit codes.
3. `reports/report_YYYY-MM-DD.md` — Daily markdown reports. Contains top picks, exploitable markets table, suspicious wallet activity, sandpit alerts, and method combo performance (top 5 by fitness).
4. `test_pipeline.py` output — 4-step pipeline test (fetch resolved markets → fetch trades → build wallet profiles → backtest combos).
5. `CLAUDE.md` Bug Tracking section — Resolved bugs (B001-B017), known issues (P001-P015), areas needing review.

**Capabilities:**

1. **Log analysis** — Parse `bot.log` for patterns:
   - Count errors/warnings per module per time window
   - Extract stack traces and group by root cause
   - Detect new error types that weren't present before a code change
   - Flag log growth anomalies (sudden burst of warnings = something broke)
   - Check for silent failures: methods returning `signal=0, confidence=0` with reason metadata

2. **Test execution & interpretation** — Run `test_pipeline.py` and interpret results:
   - Verify all 4 steps complete without exceptions
   - Check that new methods (M25-M28) execute during backtest step
   - Compare combo fitness scores against previous runs (regression detection)
   - Validate that method registration is correct: 28 methods, 6 categories

3. **Report validation** — Read latest report from `reports/` and check:
   - Are picks being generated? (empty picks = signal pipeline broken)
   - Are edge values reasonable? (negative edge or edge > 0.5 = suspicious)
   - Does the combo performance table include new methods?
   - Are madness ratios computed correctly? (NaN or 0.0 on all markets = bug)
   - Compare against previous reports: did quality degrade after a change?

4. **Regression detection** — After any code change:
   - Run the import smoke test: `from methods import CATEGORIES, METHODS; assert len(METHODS) == expected`
   - Verify no existing methods broke by checking for new exceptions in log
   - Compare method_results table: did previously-good combos lose fitness?
   - Check for import errors, missing config constants, type mismatches

5. **Bug documentation** — When an issue is found:
   - Assign the next available bug ID (B-series for resolved, P-series for known)
   - Document in the format matching CLAUDE.md Bug Tracking tables
   - Include: module, risk level, description, and proposed fix
   - Cross-reference with existing known issues (is this a recurrence of P006? P011?)

6. **Caretaker health** — Read `caretaker.log` to check:
   - How many restarts occurred? (frequent restarts = unstable dashboard)
   - What were the exit codes? (non-zero = crash, not graceful shutdown)
   - Time between restarts (decreasing interval = cascading failure)

**Safety:** Read-only access to all files. Same `validate_readonly_query.py` hook applies for any database queries. Cannot modify source code — reports findings to overseer for action.

**Input format:** Overseer provides context like:
- "Validate the M25-M28 integration" (post-change validation)
- "Check bot.log for errors in the last 24 hours" (routine health check)
- "Compare today's report against last week's" (quality tracking)
- "Run test_pipeline.py and report results" (full pipeline test)

**Output format:** Structured markdown:
- **Status:** PASS / WARN / FAIL (overall assessment)
- **Findings:** Numbered list of issues with severity (critical/warning/info)
- **Log excerpts:** Relevant error/warning lines with timestamps
- **Report comparison:** Side-by-side metrics if comparing runs
- **Bug entries:** Pre-formatted rows for CLAUDE.md Bug Tracking tables if new issues found
- **Recommendations:** Specific next steps for the overseer

**Example queries:**
- "We just added M25-M28. Validate everything still works."
- "Parse bot.log — any new errors since the last commit?"
- "Read the latest daily report. Are picks reasonable?"
- "Run test_pipeline and tell me if M methods show up in backtest results."
- "Check if caretaker has been restarting the dashboard excessively."
- "Compare reports from Feb 7, 10, and 11 — is quality trending up or down?"

**Post-change validation checklist** (run after any code modification):
1. Import test: `python -c "from methods import METHODS; print(len(METHODS))"`
2. Config test: `python -c "import config; print(config.TOTAL_METHODS)"`
3. Parse last 50 lines of `bot.log` for new ERROR/EXCEPTION entries
4. Read latest report in `reports/` — verify structure and non-empty picks
5. If methods changed: run `test_pipeline.py` step 4 (backtest) to verify execution
6. Report findings with PASS/WARN/FAIL status

### Stub Agents — Specs for Future Activation

**`method-auditor`** (activate at M2)
- Computes pairwise correlation between method signals across all tested markets
- Flags method pairs with correlation > 0.7 (redundant in combos)
- Validates each method's implementation matches its CLAUDE.md algorithm description
- Reports methods that never appear in top-50 combos (dead weight)
- Suggests category rebalancing if one category dominates or is absent from winners

**`threshold-tuner`** (activate at M3)
- For each config constant, runs sensitivity analysis: what happens to top combo fitness if the threshold shifts +/-10%, +/-25%?
- Identifies constants with high sensitivity (small change = big fitness impact) vs. low sensitivity (can be simplified)
- Proposes concrete value changes with expected fitness delta
- Respects constraints: thresholds must remain physically meaningful (e.g., probability thresholds stay in 0-1)

**`api-health-checker`** (activate at M4)
- Pings all configured endpoints, reports HTTP status and response time
- Validates response JSON schemas match expected structure (catches silent API changes)
- Tracks rate limit headers where available, warns at 80% consumption
- Checks data freshness: last trade timestamp vs. now, flags stale markets
- Runs on haiku (cheapest model — this is mechanical work, not reasoning)

**`wallet-profiler`** (activate at M5)
- Given a wallet address, pulls full trade history from `bets` table
- Computes per-market performance: win/loss, timing relative to market lifecycle, size patterns
- Runs M25 wallet regime analysis on the wallet's history across markets
- Cross-references with S1 (is this wallet flagged as sharp?), S4 (sandpit?)
- Validates rationality_score against actual behavior patterns
- Output: wallet profile card with key stats, flags, and recommendation (track/ignore/investigate)
