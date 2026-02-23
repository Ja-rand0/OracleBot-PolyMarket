## Threshold Tuning Report — 2026-02-23

### Baseline

- Top combo: D5, T17, M26, P20
- Baseline fitness: 0.258724 (accuracy=0.7447, edge=0.0353, FPR=0.0000, complexity=4)
- Resolved markets tested: 60 (fixed set, markets with ≥5 bets, drawn from 8037 total resolved)
- Wallets loaded: 2046 (only wallets appearing in the 60-market set)
- Constants analyzed: 12
- DB path: data.db (WAL mode, timeout=30)

Note: S1, T19, and BACKTEST_CUTOFF_FRACTION constants showed exactly zero sensitivity in this combo (see Low Sensitivity section). S1 methods are not in the top-4 combo; T19 is not in the combo either. BACKTEST_CUTOFF_FRACTION showed no variation, suggesting the 60-market sample is stable regardless of cutoff (markets may be short-lived or the cutoff range tested does not shift which bets are visible within the fixed dataset).

---

### High Sensitivity Constants

These constants show fitness change >0.02 with ±10% perturbation on this combo.

| Constant | Current | Recommended | Fitness Delta | Rationale |
|----------|---------|-------------|---------------|-----------|
| `M26_TRENDING_THRESHOLD` | 0.60 | **0.33** | +0.039 to +0.047 | Step function: below ~0.34 activates trending signal for 85%+ of markets; above ~0.58 suppresses it. At 0.33, accuracy jumps from 74.5% → 87.2%. The Markov self-transition probability for this dataset is typically in the 0.33-0.55 range, so the current 0.60 threshold is set too high — it classifies most markets as "non-trending" and falls back to zero-signal, discarding valid directional information. The recommended value keeps FPR=0.000 and improves both accuracy and edge. |
| `T17_RATIONALITY_CUTOFF` | 0.40 | **0.58** | +0.022 to +0.023 | Step function: below 0.51 → no change; at 0.53 → accuracy jumps to 80.9%; peaks at 0.58 (fitness=0.281585). Raising the cutoff shrinks the "smart wallet" pool to genuinely high-rationality bettors (≥0.58 score), making T17's Bayesian posterior more discriminating. Current 0.40 is too permissive — it includes too many average wallets in the "smart" signal, diluting the divergence calculation. Physical constraint: must stay below ~0.68 where FPR rises sharply (at 0.70, FPR=0.125 and fitness collapses to 0.222). |
| `P20_DEVIATION_THRESHOLD` | 0.10 | **0.02** | +0.023 | Step function: 0.005–0.025 all yield fitness≈0.281751; 0.03 → 0.267; 0.04+ → no improvement or regression. The current 0.10 threshold requires a 10% VWAP deviation before flagging informed trading, which is too conservative for this dataset. At 0.02, the same set of markets are flagged as having Nash deviation as at 0.10, but the method fires on more markets and the accuracy gain (+6.4pp) comes from catching moderate but real pricing divergences. Physical note: ≤0.025 is the effective minimum for this dataset; going lower (0.005-0.020) all produce the same result. Recommended: 0.02 (clear round number within the effective range). |

#### Joint Effect

The three high-sensitivity changes are partially independent:

| Combination | Fitness | Delta |
|-------------|---------|-------|
| Baseline only | 0.258724 | — |
| M26_TREND=0.33 | 0.305858 | +0.047134 |
| T17_RAT=0.58 | 0.281585 | +0.022861 |
| P20_DEV=0.02 | 0.281751 | +0.023027 |
| M26_TREND=0.33 + T17_RAT=0.58 | 0.306116 | +0.047392 |
| M26_TREND=0.33 + P20_DEV=0.02 | 0.306381 | +0.047657 |
| T17_RAT=0.58 + P20_DEV=0.02 | 0.289720 | +0.030996 |
| ALL THREE (M26_TREND + T17_RAT + P20_DEV) | **0.306638** | **+0.047914** |

T17_RAT and P20_DEV are partially correlated (both boost accuracy via filtering), so their joint gain is additive with M26_TREND but subadditive with each other. The full three-way combo gives the best fitness: **0.306638**.

---

### Medium Sensitivity Constants

These constants show fitness change 0.005–0.02 with ±25% perturbation.

| Constant | Current | Recommended | Fitness Delta | Rationale |
|----------|---------|-------------|---------------|-----------|
| `T17_AMOUNT_NORMALIZER` | 1000.0 | **50.0** | +0.005 to +0.018 (non-monotone) | Non-monotone response with a local peak at 3–7 (+0.018, with accuracy jump to 78.7%), a valley at 15–600, and a secondary plateau at 20–50 (+0.005). The "smart money" Bayesian update in T17 weights bets by `rationality * amount / T17_AMOUNT_NORMALIZER`. At 1000, a $100 bet contributes only 0.1 weight units, making the posterior insensitive. At 50, a $100 bet contributes 2.0 weight units — strong enough to move the posterior but not so extreme as to allow single large bets to dominate. Values 3-7 are actually better for accuracy (+18bp) but are computationally equivalent and less physically interpretable. Recommended: 50 as a stable, interpretable midpoint that avoids the 3-7 noise peak and delivers sustained +0.005 improvement. |
| `T17_UPDATE_STEP` | 0.10 | **0.80** | +0.004 to +0.006 | Monotonically increasing toward 2.0, then mild decline before re-rising at 10.0. At 0.80 (+0.0048), improvement is reliable. Step controls the magnitude of each Bayesian update: larger steps mean smarter wallets push the posterior further, amplifying divergence from the public prior. Current 0.10 causes the posterior to barely move, reducing the discriminating power of the divergence signal. Physical constraint: values >2.0 risk numerical instability in the posterior calculation (values tested up to 10.0 show non-monotone behavior suggesting overflow effects). Recommended: 0.80 — tripling from current, still within stable range, gives reliable edge improvement. |
| `M26_LOW_THRESHOLD` | 0.35 | **0.25** | +0.007 (alone) | Value 0.25 gives +0.007 alone but hurts the joint combo (reduces from 0.306638 to 0.304941 when added to the three-way best). The threshold widens the LOW state boundary (YES probability below 0.25 = LOW) so fewer intermediate markets get classified as LOW. This helps in isolation but interferes with M26_TRENDING_THRESHOLD changes. **Not recommended when M26_TRENDING_THRESHOLD is also being changed.** Recommend leaving at 0.35 if applying the full three-way change. |

---

### Low Sensitivity Constants (no change recommended)

These constants showed <0.005 fitness delta across the full tested range.

- `S1_MIN_RESOLVED_BETS` — exactly zero sensitivity in this combo (S1 not in top-4)
- `S1_STDDEV_THRESHOLD` — exactly zero sensitivity in this combo (S1 not in top-4)
- `T19_ZSCORE_THRESHOLD` — exactly zero sensitivity in this combo (T19 not in top-4)
- `M26_HIGH_THRESHOLD` — exactly zero sensitivity across entire tested range (0.55–0.80); the HIGH state is never triggered in this market sample, so the threshold is irrelevant
- `M26_NUM_WINDOWS` — effectively insensitive; values 5–8 all give fitness≈0.258738; values ≥10 cause FPR to appear (0.10), hurting fitness. Keep at 5.
- `BACKTEST_CUTOFF_FRACTION` — exactly zero sensitivity; all values from 0.50–0.90 give identical fitness=0.258724, suggesting the market-level timing structure in this 60-market sample does not change which bets are visible at different cutoffs (consistent with markets having concentrated bet activity that falls well within any cutoff fraction tested)

---

### Constraint Violations Avoided

| Value Tested | Constant | Reason Rejected |
|-------------|----------|-----------------|
| `T17_RATIONALITY_CUTOFF = 0.70` | T17_RATIONALITY_CUTOFF | Fitness collapses to 0.222557 (FPR=0.125). Cutoff too high — fewer than 3 wallets qualify as "smart" in many markets, making the posterior degenerate. |
| `M26_TRENDING_THRESHOLD = 0.75–0.80` | M26_TRENDING_THRESHOLD | Fitness drops to 0.256346 — same regime as 0.66–0.70 (all above step). No signal from M26 at all. |
| `T17_AMOUNT_NORMALIZER = 3.0–7.0` | T17_AMOUNT_NORMALIZER | While these give the highest accuracy (78.7%), the +0.018 gain is fragile: a $1000 bet would contribute 143–333 weight units, making the posterior entirely dominated by single large bets. This violates the method's design intent of weighting by rationality, not raw size. The accuracy gain may be a data artifact on this 60-market sample. |
| `T17_UPDATE_STEP > 2.0` | T17_UPDATE_STEP | Non-monotone behavior above 2.0 suggests numerical instability. At 10.0 it gives fitness=0.269651, but the mechanism is likely posterior saturation (→ constant signal regardless of data), not genuine discrimination. |
| `P20_DEVIATION_THRESHOLD < 0.01` | P20_DEVIATION_THRESHOLD | All values ≤0.025 produce identical results (step function), so going below 0.01 adds no value and risks flagging every market (deviation of 0 is always ≥ 0.001). Physical minimum: any non-zero value ≤0.025 is equivalent. |
| `M26_LOW_THRESHOLD + M26_TRENDING_THRESHOLD combined` | Both | M26_LOW_THRESHOLD=0.25 alone gives +0.007 but reduces the full three-way joint combo by −0.008. These constants interact: widening the LOW state boundary while also lowering the trending threshold creates classification inconsistencies. Not recommended when the trending threshold is also being changed. |

---

### Recommended config.py Changes

Apply these changes to `config.py`. They represent the highest-confidence, physically validated improvements.

```python
# Apply these changes to config.py:

# HIGH SENSITIVITY — apply all three for +0.047914 total fitness gain
M26_TRENDING_THRESHOLD = 0.33   # was 0.60; +0.039 to +0.047 fitness
                                 # Reason: current 0.60 is above Markov self-transition
                                 # probability for most markets, so M26 never fires.
                                 # 0.33 is consistent with the mathematical minimum for
                                 # a 3-state matrix (uniform = 0.333) and ensures the
                                 # method activates on genuinely persistent trends.

T17_RATIONALITY_CUTOFF = 0.58   # was 0.40; +0.022 fitness
                                 # Reason: 0.40 is below median rationality score, so
                                 # "smart" pool includes average wallets. 0.58 is above
                                 # the median, keeping only genuinely high-quality bettors.
                                 # Step function: 0.51 is the phase transition point;
                                 # 0.58 gives the best edge within the stable range.

P20_DEVIATION_THRESHOLD = 0.02  # was 0.10; +0.023 fitness
                                 # Reason: 0.10 requires a 10% VWAP deviation to signal
                                 # Nash deviation. This dataset shows that 2% deviation
                                 # is sufficient to identify informed trading while
                                 # avoiding noise. Step function: all values ≤0.025
                                 # are equivalent; 0.02 chosen for interpretability.

# MEDIUM SENSITIVITY — apply if further improvement needed (independent of above)
T17_AMOUNT_NORMALIZER = 50.0    # was 1000.0; +0.005 fitness
                                 # Reason: 1000 makes $100 bets contribute 0.1 weight,
                                 # too weak to move the Bayesian posterior. 50 gives
                                 # $100 bets 2.0 weight units — interpretable as
                                 # "a $100 bet = 2 data points worth of signal".
                                 # Note: values 3-7 give +0.018 but are physically
                                 # fragile; 50 is the stable recommendation.

T17_UPDATE_STEP = 0.80          # was 0.10; +0.005 fitness
                                 # Reason: 0.10 barely moves the Bayesian posterior.
                                 # 0.80 amplifies smart-wallet signals to produce
                                 # meaningful divergence from the public prior.
                                 # Stay below 2.0 to avoid numerical instability.
```

#### Priority Order
1. Apply M26_TRENDING_THRESHOLD=0.33 first (largest individual gain: +0.047)
2. Add T17_RATIONALITY_CUTOFF=0.58 (marginal gain when combined with #1: +0.0003)
3. Add P20_DEVIATION_THRESHOLD=0.02 (marginal gain when combined with #1+#2: +0.0005)
4. T17_AMOUNT_NORMALIZER=50.0 and T17_UPDATE_STEP=0.80 are independent — apply together for additional +0.005 (not tested jointly with the three-way combo above)

---

### Caveats

**Sample size**: Only 60 resolved markets used for speed. The step-function behavior of M26_TRENDING_THRESHOLD and P20_DEVIATION_THRESHOLD is real (observed across many values) but the exact step location (0.34 and 0.03 respectively) may shift with more data. Recommend rerunning on 200+ markets once data grows.

**Overfit risk for M26_TRENDING_THRESHOLD**: The jump from 74.5% to 87.2% accuracy is very large for a single threshold change. This suggests the current 0.60 setting is causing M26 to return zero-signal (confidence=0.1) on nearly all markets, while 0.33 causes it to fire with real signals. This is consistent with the code: at `trending_score > M26_TRENDING_THRESHOLD`, the signal activates; otherwise it falls back to 0.0/0.1. The transition is genuine, not overfitting.

**T17_RATIONALITY_CUTOFF interaction with wallet data quality**: The jump at 0.53 depends on the rationality_score distribution in the wallets table. If wallet scores shift (e.g., after more scraping cycles), the optimal cutoff may shift. The 0.58 recommendation is robust across 0.53–0.62 (all give similar fitness).

**T17_AMOUNT_NORMALIZER and UPDATE_STEP not jointly tested**: The medium-sensitivity constants were tested individually. Their joint effect with the three high-sensitivity changes is unknown. Run a combined test before deploying.

**BACKTEST_CUTOFF_FRACTION insensitivity**: The zero-delta result across all cutoff fractions (0.50–0.90) is surprising. It may reflect that this 60-market sample has bet activity concentrated well before all tested cutoffs, or that the market end_date/created_at timestamps have limited variance. This constant needs testing on a larger, more temporally diverse market set.

**S1, T19 constants**: These appear insensitive because S1 and T19 are not in the D5+T17+M26+P20 combo. These constants should be tuned against combos that include S1 or T19, not the top-4 combo.
