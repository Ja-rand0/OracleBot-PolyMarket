# Polymarket Prediction Bot — Project Brief

## Overview

Build a read-only analytics bot that detects sharp/insider money on Polymarket by filtering out emotional/irrational bets, applying discrete math and statistical methods, and brute-force testing all method combinations to find the optimal prediction formula.

The bot does NOT place bets. It analyzes, filters, logs, and reports. Betting functionality is a future phase if results prove useful.

---

## Architecture

- **Language:** Python 3.11+
- **Storage:** SQLite (single file DB, no server needed)
- **Data Source:** Polymarket CLOB API + Polygon on-chain data
- **Scheduling:** Cron job or simple loop with sleep (data pull every 15 min)
- **Output:** Daily report (CLI + optional markdown file)
- **Hosting (later):** Free VPS (Railway, Render, Oracle Cloud) — for now, runs locally

---

## Project Structure

```
polymarket-bot/
├── config.py              # API endpoints, constants, weights
├── main.py                # Entry point, scheduler
├── data/
│   ├── scraper.py         # Polymarket API + Polygon data ingestion
│   ├── db.py              # SQLite schema, read/write helpers
│   └── models.py          # Data classes (Bet, Wallet, Market, etc.)
├── methods/
│   ├── __init__.py        # Method registry (all 24 methods registered here)
│   ├── suspicious.py      # S1-S4: Wallet suspicion detection
│   ├── discrete.py        # D5-D9: Discrete math methods
│   ├── emotional.py       # E10-E16: Emotional bias filters
│   ├── statistical.py     # T17-T19: Statistical analysis
│   └── psychological.py   # P20-P24: Psych/sociological signals
├── engine/
│   ├── combinator.py      # Brute-force combination testing (Tier 1-3)
│   ├── backtest.py        # Backtesting framework against historical data
│   ├── fitness.py         # Fitness/scoring function for combo evaluation
│   └── report.py          # Generate daily analysis reports
├── tests/
│   └── ...                # Unit tests per module
├── data.db                # SQLite database (generated at runtime)
└── requirements.txt       # Dependencies
```

---

## Phase 1: Data Collection

### 1a. Scraper (`data/scraper.py`)

Pull from Polymarket's public CLOB API:
- All active markets (title, description, resolution criteria, end date)
- Order book / trade history per market
- Individual trade data: wallet address, side (YES/NO), amount, price/odds, timestamp

Pull from Polygon blockchain (via public RPC or Polygonscan API):
- Wallet transaction history for flagged wallets
- Token transfer patterns between wallets
- Wallet age and activity history

### 1b. Database Schema (`data/db.py`)

```sql
CREATE TABLE markets (
    id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    end_date TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    outcome TEXT,  -- actual result once resolved
    created_at TEXT
);

CREATE TABLE bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT,
    wallet TEXT,
    side TEXT,        -- YES or NO
    amount REAL,
    odds REAL,        -- price at time of bet (0.0 to 1.0)
    timestamp TEXT,
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

CREATE TABLE wallets (
    address TEXT PRIMARY KEY,
    first_seen TEXT,
    total_bets INTEGER DEFAULT 0,
    total_volume REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    rationality_score REAL DEFAULT 0,
    flagged_suspicious BOOLEAN DEFAULT FALSE,
    flagged_sandpit BOOLEAN DEFAULT FALSE
);

CREATE TABLE wallet_relationships (
    wallet_a TEXT,
    wallet_b TEXT,
    relationship_type TEXT,  -- 'coordination', 'funding', 'copy_trading'
    confidence REAL,
    PRIMARY KEY (wallet_a, wallet_b)
);

CREATE TABLE method_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combo_id TEXT,          -- e.g. "S1,S2,E14,T17"
    methods_used TEXT,      -- JSON array of method IDs
    accuracy REAL,
    edge_vs_market REAL,
    false_positive_rate REAL,
    complexity INTEGER,
    fitness_score REAL,
    tested_at TEXT
);
```

---

## Phase 2: The 24 Methods

Each method is a function that takes market data + bet data and returns a score or filter result. Every method must conform to this interface:

```python
# Every method signature:
def method_name(market: Market, bets: list[Bet], wallets: dict[str, Wallet]) -> MethodResult:
    """
    Returns:
        MethodResult with:
            - signal: float (-1.0 to 1.0, negative = NO, positive = YES)
            - confidence: float (0.0 to 1.0)
            - filtered_bets: list[Bet] (bets remaining after this filter, if applicable)
            - metadata: dict (any extra info for debugging)
    """
```

### Category S: Suspicious Wallet Detection

**S1 — Win Rate Outlier Detection**
- Calculate each wallet's historical win rate across all resolved markets
- Flag wallets with win rates > 2 standard deviations above the mean
- Wallets with < 10 resolved bets are excluded (insufficient data)

**S2 — Bet Timing Relative to Resolution**
- For each bet, calculate: time_remaining = market_end - bet_timestamp
- Flag bets placed in the final 10% of a market's lifespan with high conviction (large amount, extreme odds)
- Score: ratio of late-stage large bets to total bets for that wallet

**S3 — Wallet Coordination Clustering**
- Build a temporal graph: if wallet A and wallet B bet the same side within N minutes of each other across M+ markets, draw an edge
- Use community detection (Louvain algorithm) to find clusters
- Clusters of 3+ wallets acting in coordination = suspicious group

**S4 — Sandpit/Bait Account Filtering**
- Detect wallets that: won big once then consistently lose, place opposing bets from linked wallets, create new wallets with suspiciously timed large deposits
- These wallets are EXCLUDED from the "smart money" pool — they're traps
- Check for wallets that manipulate odds then exit before resolution

### Category D: Discrete Math Methods

**D5 — Vacuous Truth / Implication Logic**
- Model market conditions as logical implications (P → Q)
- Identify markets where the antecedent (P) is very unlikely to be true
- If P is almost certainly false, the market resolves predictably regardless of Q
- Score based on how "vacuously safe" the bet is

**D6 — Graph Theory Wallet Mapping**
- Build a directed graph of wallet interactions (fund flows, copy-trading patterns)
- Calculate PageRank — high PageRank wallets are "influential"
- Track which direction influential wallets bet
- Weight their signal higher in the overall prediction

**D7 — Pigeonhole Principle Noise Filtering**
- If a market has N large winning bets but the maximum plausible number of insiders is M (where M < N), then at least N - M winners are lucky, not informed
- Use this to discount the apparent "signal" in markets where too many people seem to have insider info (it's noise)

**D8 — Boolean SAT Market Structure**
- Model multi-condition markets as SAT problems
- Each condition is a boolean variable
- Enumerate: under how many truth assignments does YES win vs NO?
- If 80%+ of assignments favor one side, the market structure itself is skewed — bet accordingly

**D9 — Set Partitioning (Clean vs Noise)**
- This is the master filter: U = all bets, E = emotional bets (from category E methods), S = U \ E
- All subsequent analysis runs on set S only
- Track the ratio |E| / |U| per market as an additional signal (high emotion ratio = potentially exploitable market)

### Category E: Emotional Bias Filters

**E10 — Hometown/Loyalty Bias Detection**
- For sports/political markets: check if a wallet consistently bets the same team/candidate across all markets regardless of odds
- Consistency ratio > 0.8 for one side across 5+ markets = loyalty bias
- These bets are moved to set E (emotional)

**E11 — Recency Bias Detection**
- Check if bet direction correlates with the most recent outcome in a related market
- Example: Team X won last game → disproportionate YES bets on Team X next game
- Measure correlation between recent outcomes and bet direction per wallet

**E12 — Revenge Betting Patterns**
- Detect wallets that: lost on market A, then immediately placed a larger bet on a similar market
- Pattern: loss → increased position size within 24 hours on same category
- These bets are emotional, move to set E

**E13 — Hype/Media Cycle Correlation**
- Track bet volume spikes and correlate with news/social media activity
- If bet volume spikes 3x+ within hours of major media coverage with no fundamental change to the market conditions, those spike bets are likely hype-driven
- Flag the bets placed during the spike window

**E14 — Odds Sensitivity Scoring**
- Rational bettors adjust their position as odds move. Emotional bettors bet the same regardless
- For each wallet: measure correlation between their bet size and current odds
- Low correlation = emotional (they bet $100 whether odds are 0.3 or 0.7)
- High correlation = rational (they size up when odds are favorable)

**E15 — Position Sizing Precision**
- Emotional bets tend to be round numbers: $50, $100, $500, $1000
- Sharp money is precisely sized to expected value: $437, $2,183
- Score each bet: round_number_penalty = 1.0 if amount is divisible by 50, scaled down for more precise amounts
- High round-number ratio for a wallet = likely emotional bettor

**E16 — Bipartite Graph Pruning**
- Build a bipartite graph: wallets on left, outcomes on right
- Draw edges for each bet (wallet → outcome they bet on)
- Emotional bettors have edges heavily skewed to one side
- Prune wallets where edge distribution divergence (KL divergence from uniform) exceeds threshold

### Category T: Statistical Methods

**T17 — Bayesian Updating**
- Start with a prior probability for each market outcome (use initial market odds as prior)
- As each bet comes in, update the posterior based on bet size and wallet rationality score
- The divergence between the "public posterior" (all bets) and "smart posterior" (filtered bets only) is the signal
- Large divergence = smart money disagrees with the public

**T18 — Benford's Law**
- Analyze the leading digit distribution of bet amounts in each market
- Natural financial data follows Benford's distribution (30% start with 1, 17% with 2, etc.)
- Markets where bet amounts significantly deviate from Benford's may have manufactured/coordinated betting activity
- Use chi-squared test against expected Benford distribution

**T19 — Z-Score Outlier Detection**
- For each market: calculate mean and std dev of bet amounts
- Flag individual bets with z-score > 2.5 as statistical outliers
- These aren't necessarily emotional — they might be the sharp money signal
- Cross-reference with wallet rationality score to categorize

### Category P: Psychological/Sociological Methods

**P20 — Nash Equilibrium Deviation**
- Calculate the theoretical Nash equilibrium for market odds (where no bettor can improve their expected value by changing their bet)
- Current market odds that deviate significantly from Nash equilibrium suggest information asymmetry
- The direction of deviation suggests which side has private information

**P21 — Prospect Theory Exploitation**
- Per Kahneman/Tversky: people overweight small probabilities and underweight large ones
- Markets with very low probability events (< 10%) are systematically overbet by emotional money
- Markets with very high probability events (> 90%) are underbet relative to true probability
- Score: expected mispricing based on prospect theory's probability weighting function

**P22 — Herding Behavior Detection**
- Measure temporal clustering of bets: if N wallets bet the same side within a short window
- Calculate the "independence score": would this betting pattern occur if bettors were acting independently?
- Low independence = herding. Herding bets get partially discounted (not fully removed — sometimes the herd is right)

**P23 — Anchoring Bias Tracking**
- Identify the first large bet in each market (the "anchor")
- Measure how much subsequent bets cluster around the anchor's implied probability
- High anchoring effect = the market hasn't fully processed new information
- Opportunity: if fundamentals suggest a different probability than the anchor, there's an exploitable gap

**P24 — Wisdom vs Madness Ratio**
- For each market: calculate |set E| / |set U| (what percentage of bets are emotional)
- Low ratio (< 0.3) = "wisdom of crowds" — market is probably efficient, hard to beat
- High ratio (> 0.7) = "madness of crowds" — market is probably inefficient, potentially exploitable
- This ratio is a meta-signal: it tells you WHICH markets to focus on, not which side to bet

---

## Phase 3: Brute-Force Combination Testing

### Tier 1 — Within-Category Testing (`engine/combinator.py`)

Test all combinations within each category independently:
- S category: 2^4 - 1 = 15 combos
- D category: 2^5 - 1 = 31 combos
- E category: 2^7 - 1 = 127 combos
- T category: 2^3 - 1 = 7 combos
- P category: 2^5 - 1 = 31 combos
- **Total Tier 1: 211 tests**

For each combo:
1. Run all methods in the combo against historical data
2. Combine their signals (weighted average, where weights are initially equal)
3. Evaluate using the fitness function
4. Record results in `method_results` table

Select top 3 performers per category → 15 finalist sub-models.

### Tier 2 — Cross-Category Testing

Take the 15 finalists from Tier 1.
Test all combos: 2^15 - 1 = 32,767 tests.

Same process: run combo, evaluate fitness, record results.

Select top 10 overall combos.

### Tier 3 — Fine-Tuning

For each of the top 10 combos from Tier 2:
- Try adding each unused method one at a time
- Try removing each included method one at a time
- If any add/remove improves fitness, apply it
- Repeat until no single change improves the score (hill climbing)

This catches methods that only shine in cross-category combinations.

### Fitness Function (`engine/fitness.py`)

```python
def calculate_fitness(combo_results: ComboResults) -> float:
    """
    combo_results contains:
        - accuracy: float (% of correct predictions on resolved markets)
        - edge_vs_market: float (% improvement over raw market odds)
        - false_positive_rate: float (% of flagged "sharp" bets that were wrong)
        - complexity: int (number of methods in combo)
    """
    fitness = (
        combo_results.accuracy * 0.35
        + combo_results.edge_vs_market * 0.35
        - combo_results.false_positive_rate * 0.20
        - (combo_results.complexity / 24) * 0.10  # normalize complexity to 0-1
    )
    return fitness
```

Weights (0.35, 0.35, 0.20, 0.10) are starting values. Can be tuned later.

---

## Phase 4: Backtesting (`engine/backtest.py`)

### Data Needed
- Historical resolved Polymarket markets (as many as possible)
- All bet history for those markets (wallet, amount, side, odds, timestamp)
- Actual outcomes

### Process
For each resolved market in the historical dataset:
1. Replay bets in chronological order
2. At a configurable cutoff point (e.g., 75% through the market's lifespan), run the current method combo
3. Record the combo's prediction (YES/NO + confidence)
4. Compare to actual outcome
5. Calculate hypothetical profit/loss if a bet was placed at that point

### Output
- Accuracy per combo
- Cumulative P&L per combo
- Sharpe ratio equivalent (return / volatility of returns)
- Max drawdown

---

## Phase 5: Daily Reporting (`engine/report.py`)

Generate a daily markdown report:

```markdown
# Polymarket Bot — Daily Report (YYYY-MM-DD)

## Top Exploitable Markets (High Madness Ratio)
| Market | Madness Ratio | Smart Money Side | Confidence |
|--------|---------------|------------------|------------|
| ...    | ...           | ...              | ...        |

## Suspicious Wallet Activity
| Wallet | Win Rate | Recent Bet | Amount | Market |
|--------|----------|------------|--------|--------|
| ...    | ...      | ...        | ...    | ...    |

## Sandpit Alerts (Wallets to Avoid)
| Wallet | Reason | Confidence |
|--------|--------|------------|
| ...    | ...    | ...        |

## Method Combo Performance (Rolling 30-day)
| Combo | Accuracy | Edge | Fitness |
|-------|----------|------|---------|
| ...   | ...      | ...  | ...     |
```

---

## Dependencies (`requirements.txt`)

```
requests
pandas
numpy
scipy
networkx          # graph theory (D6, S3, E16)
python-louvain    # community detection (S3)
scikit-learn      # clustering, outlier detection
schedule          # cron-like scheduling
```

---

## Implementation Order

1. **`data/models.py`** — Define data classes first
2. **`data/db.py`** — Set up SQLite schema
3. **`data/scraper.py`** — Get data flowing from Polymarket API
4. **`config.py`** — API endpoints, constants
5. **`methods/*.py`** — Implement all 24 methods (start with the simpler ones: E15, T19, S1)
6. **`engine/fitness.py`** — Fitness function
7. **`engine/backtest.py`** — Backtesting framework
8. **`engine/combinator.py`** — Tier 1-3 combo testing
9. **`engine/report.py`** — Daily reports
10. **`main.py`** — Wire it all together

---

## Key Reminders

- This is READ-ONLY. No bet placement functionality. We are observing and analyzing only.
- Every method must follow the standard interface returning MethodResult with signal, confidence, filtered_bets, and metadata.
- SQLite only. No external database servers.
- Start with data collection and simple methods. Get data flowing before optimizing.
- The brute-force combinator is the core value prop — make it thorough and well-logged.
- All timestamps should be UTC.
- Handle API rate limits gracefully with retries and backoff.
- Log everything. When in doubt, log more.
