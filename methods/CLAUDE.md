# Detection Methods — Full Algorithm Reference

> This file is loaded when working in the `methods/` directory.
> Summary table (names + what each detects): root `CLAUDE.md`

---

## Category S — Suspicious Wallet Detection (S1-S4)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **S1** | Win Rate Outlier | Wallets with statistically abnormal win rates | Flag wallets with win rate > mean + `S1_STDDEV_THRESHOLD` * stddev. Requires `S1_MIN_RESOLVED_BETS` minimum. Signal = YES/NO volume ratio of sharp wallets. Confidence scales with number of sharp wallets (cap at 10). |
| **S3** | Coordination Clustering | Coordinated wallet groups betting together | Builds co-occurrence graph: wallets betting same side within `S3_TIME_WINDOW_MINUTES` window. Requires ≥2 co-occurrences per edge. Runs Louvain community detection. Flags clusters ≥ `S3_MIN_CLUSTER_SIZE`. Min 10 bets to skip expensive graph ops. **Deps**: networkx, python-louvain. |
| **S4** | Sandpit Filter | Bait/trap accounts that distort the signal | Three patterns: (1) flagged_sandpit wallets, (2) ≥`S4_SANDPIT_MIN_BETS` bets + <`S4_SANDPIT_MAX_WIN_RATE` win rate + >`S4_SANDPIT_MIN_VOLUME` volume (consistent losers), (3) ≤`S4_NEW_WALLET_MAX_BETS` total bets + any single bet >`S4_NEW_WALLET_LARGE_BET` (suspiciously large first bet). Returns cleaned bet list. |

---

## Category D — Discrete Math Methods (D5-D9)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **D5** | Vacuous Truth | Markets where structure makes one outcome near-certain | Checks median odds: if ≥0.95 → YES certain, if ≤0.05 → NO certain. Confidence = distance from 0.90/0.10 boundary. This filters out markets that are already settled. |
| **D7** | Pigeonhole Noise | Too many "sharp" wallets (most are just lucky) | Estimates max plausible insiders as sqrt(active_wallets). If actual sharp count exceeds this, applies noise discount. Signal = raw volume signal * (1 - noise_ratio). Uses `D7_MIN_BETS` threshold (not S1's). |
| **D8** | Boolean SAT | Structural bet distribution skew | If ≥80% of bets favor one side, the structure itself is skewed. Linear signal mapping for balanced markets. Simple bet count ratio analysis. |
| **D9** | Set Partition | Clean vs. emotional bet separation | Partitions bets by wallet rationality_score (<0.4 = emotional). Signal from clean bets only. Higher emotion_ratio = market is more exploitable = higher confidence. Master filter method. |

---

## Category E — Emotional Bias Filters (E10-E16)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **E10** | Loyalty Bias | Wallets that always bet the same side | Flags wallets with ≥`E10_MIN_MARKETS` bets where ≥`E10_CONSISTENCY_THRESHOLD` are on one side. Removes from signal. |
| **E11** | Recency Bias | Early bets extrapolating from recent events | Compares first-20% bet ratio to remaining-80%. If skew >0.3, filters wallets that only bet early (and didn't return later with information). |
| **E12** | Revenge Betting | Tilt/chase behavior after losses | Detects bet size increasing ≥1.5x within `E12_WINDOW_HOURS` hours, with current bet >$100. These are emotional doublings-down. |
| **E13** | Hype Detection | Volume spikes from media/social attention | Buckets bets hourly. Flags hours where volume ≥ `E13_VOLUME_SPIKE_MULTIPLIER` * median hourly volume. Removes spike-window bets. Uses `set` membership for O(1) filtering. |
| **E14** | Odds Sensitivity | Bettors who don't adjust size with odds | Computes correlation between bet amount and odds per wallet. Low correlation (< `E14_LOW_CORRELATION_THRESHOLD`) = emotional (flat betting regardless of edge). |
| **E15** | Round Numbers | Emotional bets at round amounts ($50, $100, $500) | Flags wallets where >70% of bets are divisible by `E15_ROUND_DIVISOR`. Sharp money uses precise sizing. |
| **E16** | KL Divergence | Wallets with extreme YES/NO skew | Computes KL divergence of each wallet's YES/NO ratio from uniform (0.5, 0.5). Wallets above `E16_KL_THRESHOLD` are biased. |

---

## Category T — Statistical Analysis (T17-T19)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **T17** | Bayesian Updating | Smart vs. public opinion divergence | Computes two posteriors from the same prior: (1) public (all bets), (2) smart (only rationality ≥`T17_RATIONALITY_CUTOFF` wallets, weighted by rationality * `T17_AMOUNT_NORMALIZER`). Update step = `T17_UPDATE_STEP`. Signal = divergence * 5, confidence = divergence * 3. **Deps**: scipy. |
| **T18** | Benford's Law | Manufactured/coordinated bet amounts | Extracts leading digits of bet amounts, tests against Benford's distribution via chi-squared (df=8). p-value < `T18_CHI_SQUARED_PVALUE` = suspicious. Non-directional signal (flags the market, not a side). Min 20 bets. **Deps**: scipy. |
| **T19** | Z-Score Outlier | Statistically unusual bet sizes | Flags bets with z-score > `T19_ZSCORE_THRESHOLD`. Cross-references with wallet rationality: high-rationality outliers = sharp money signal, low-rationality = noise. |

---

## Category P — Psychological / Sociological Signals (P20-P24)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **P20** | Nash Deviation | Information asymmetry via price divergence | Compares VWAP (equilibrium proxy) to last-10-bet average price. Deviation > `P20_DEVIATION_THRESHOLD` suggests informed trading is pushing the marginal price away from equilibrium. |
| **P21** | Prospect Theory | Kahneman/Tversky probability weighting mispricing | Applies the probability weighting function (gamma=0.61): `w(p) = p^gamma / (p^gamma + (1-p)^gamma)^(1/gamma)`. Low-probability events are over-bet (signal NO), high-probability events are under-bet (signal YES). Thresholds: `P21_LOW_PROB`, `P21_HIGH_PROB`. Note: formula approximation may not match exact T-K paper — see P004. |
| **P22** | Herding | Temporal clustering of same-side bets | O(n) two-pointer sliding window detects max same-side cluster. Compares to expected cluster under random betting. If herding detected (independence_score <0.5), discounts signal by 50%. Min `P22_MIN_HERD_SIZE` bets in `P22_TIME_WINDOW_MINUTES` window. |
| **P23** | Anchoring | Market stuck on the first large bet's price | Finds anchor = first bet ≥ `P23_ANCHOR_MIN_AMOUNT`. Measures how much subsequent bets cluster around anchor odds (mean absolute diff). If anchoring_strength >0.7, signal = direction of late money (which may disagree with the anchor). |
| **P24** | Wisdom vs Madness | Market efficiency estimator | Meta-signal: measures what % of bets are emotional (rationality <0.4). High ratio (> `P24_HIGH_RATIO`) = "madness of crowds" → market is exploitable, trust signal. Low ratio (< `P24_LOW_RATIO`) = "wisdom of crowds" → market is efficient, dampen signal. |

---

## Category M — Markov Chain / Temporal Transition Analysis (M26-M28)

| ID | Name | What It Detects | Algorithm |
|----|------|-----------------|-----------|
| **M26** | Market Phases | Trending vs. mean-reverting market price dynamics | Divides timeline into `M26_NUM_WINDOWS` windows. Classifies each by median YES-prob: LOW (<`M26_LOW_THRESHOLD`)/MID/HIGH (>`M26_HIGH_THRESHOLD`). Builds 3×3 transition matrix. Trending score = average self-transition probability. If > `M26_TRENDING_THRESHOLD`, signal = direction of last state. |
| **M27** | Flow Momentum | Persistent directional bet flow vs. oscillation | Divides into `M27_NUM_WINDOWS` windows. Net dollar flow per window → YES_HEAVY (>`M27_FLOW_THRESHOLD`)/BALANCED/NO_HEAVY. Momentum score = `(P(Y→Y) + P(N→N)) / 2`. If > `M27_MOMENTUM_THRESHOLD`, signal follows flow. High reversal → contrarian signal. |
| **M28** | Smart-Follow | Smart money leading retail in temporal betting order | Splits wallets: smart (rationality ≥`M28_SMART_THRESHOLD`, min `M28_MIN_SMART_WALLETS`) and retail (<`M28_RETAIL_THRESHOLD`, min `M28_MIN_RETAIL_WALLETS`). Per `M28_NUM_WINDOWS` time windows: who bets first? Builds SMART_LEADS/MIXED/RETAIL_LEADS transition matrix. If smart leads persistently, signal = smart money direction. Contrarian amplification when retail leads opposite. |

---

## Wallet Rationality Formula

`rationality_score = win_rate * 0.5 + (1 - round_ratio) * 0.3`

Range: [0.0, 0.8]. Weights are provisional heuristics — needs validation against backtest data (see Areas Needing Review in root CLAUDE.md). The `+0.2` constant floor was removed (B036) because it inflated all wallets equally and prevented the score from reaching 0.0.
Used as threshold in: D9 (<0.4 = emotional), T17 (≥`T17_RATIONALITY_CUTOFF`), T19, M28.
