# OracleBot

A read-only analytics bot that detects **sharp money** (informed/insider bets) on Polymarket by filtering out emotional and irrational bets using behavioral economics, then brute-force testing method combinations for optimal signal extraction.

**Core Philosophy:** Most bettors exhibit irrational, emotional, or manipulative behaviors. By identifying and filtering these out, the bot uncovers the true underlying signal driven by informed participants.

## Detection Methods (28 total, 6 categories)

- **S (Suspicious):** Wallet-level anomaly detection — win rate outliers, bet timing, coordination clustering, sandpit filtering
- **D (Discrete):** Structural analysis — PageRank influence, pigeonhole noise, Boolean SAT, set partitioning
- **E (Emotional):** Bias filtering — loyalty, recency, revenge betting, hype detection, round numbers, KL divergence
- **T (Statistical):** Bayesian updating, Benford's law, z-score outlier detection
- **P (Psychological):** Nash deviation, prospect theory, herding, anchoring, wisdom vs. madness
- **M (Markov):** Temporal transition analysis — wallet regime detection, market phase transitions, bet flow momentum, smart-follow sequencing

Methods are combined and tested via a 3-tier brute-force combinator (within-category → cross-category → hill-climb) scored by a fitness function balancing accuracy, edge, false positive rate, and complexity.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Usage

```bash
python main.py init       # Initialize database
python main.py collect    # Fetch market and trade data
python main.py analyze    # Run backtesting and optimization
python main.py run        # Continuous collect + analyze loop
```

Or launch the dashboard via `oracle.bat`.

## AI Experimentation

This project was developed by Claude to test its capabilities in understanding, building, and refining software in the context of market analysis and automation.
