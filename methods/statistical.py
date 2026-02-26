"""T17-T19: Statistical analysis methods."""
from __future__ import annotations

import logging
import math
from collections import Counter

import numpy as np
from scipy import stats

import config
from data.models import Bet, Market, MethodResult, Wallet
from methods import register

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# T17 — Bayesian Updating
# ---------------------------------------------------------------------------
@register("T17", "T", "Bayesian updating — smart vs public posterior divergence")
def t17_bayesian(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Compare 'public posterior' (all bets) vs 'smart posterior' (rational bets only).
    Large divergence = smart money disagrees with the public."""

    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    # Prior: initial market odds (use first few bets' median odds as proxy)
    sorted_bets = sorted(bets, key=lambda b: b.timestamp)
    early = sorted_bets[:max(1, len(sorted_bets) // 10)]
    prior = float(np.median([b.odds for b in early]))
    prior = max(0.01, min(0.99, prior))

    # Public posterior: update with all bets
    # Normalize weight by len(bets) so the accumulator is scale-invariant —
    # without this, large markets overflow ±500 and both posteriors collapse
    # to the same extreme, zeroing out the divergence signal.
    n = len(bets)
    public_log_odds = math.log(prior / (1 - prior))
    for b in bets:
        weight = b.amount / config.T17_AMOUNT_NORMALIZER / n
        if b.side == "YES":
            public_log_odds += weight * config.T17_UPDATE_STEP
        else:
            public_log_odds -= weight * config.T17_UPDATE_STEP

    public_log_odds = max(-500.0, min(500.0, public_log_odds))
    public_posterior = 1 / (1 + math.exp(-public_log_odds))

    # Smart posterior: update with rational bets only
    smart_log_odds = math.log(prior / (1 - prior))
    smart_count = 0
    for b in bets:
        w = wallets.get(b.wallet)
        rationality = w.rationality_score if w else 0.5
        if rationality < config.T17_RATIONALITY_CUTOFF:
            continue  # skip emotional bets
        smart_count += 1
        weight = b.amount / config.T17_AMOUNT_NORMALIZER / n * rationality
        if b.side == "YES":
            smart_log_odds += weight * config.T17_UPDATE_STEP
        else:
            smart_log_odds -= weight * config.T17_UPDATE_STEP

    smart_log_odds = max(-500.0, min(500.0, smart_log_odds))
    smart_posterior = 1 / (1 + math.exp(-smart_log_odds))

    # Signal: where smart money points
    divergence = smart_posterior - public_posterior
    signal = max(-1.0, min(1.0, divergence * 5))  # amplify small divergences
    confidence = min(1.0, abs(divergence) * 3 + 0.1)

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "prior": prior,
            "public_posterior": public_posterior,
            "smart_posterior": smart_posterior,
            "divergence": divergence,
            "smart_bets": smart_count,
        },
    )


# ---------------------------------------------------------------------------
# T18 — Benford's Law
# ---------------------------------------------------------------------------
BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


@register("T18", "T", "Benford's Law analysis on bet amounts")
def t18_benfords_law(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Check if bet amount leading digits follow Benford's distribution.
    Deviation suggests manufactured/coordinated activity."""

    amounts = [b.amount for b in bets if b.amount >= 1]
    if len(amounts) < 20:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "insufficient bets"})

    # Extract leading digits
    leading_digits = []
    for a in amounts:
        s = str(int(a))
        if s and s[0] != '0':
            leading_digits.append(int(s[0]))

    if not leading_digits:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    n = len(leading_digits)
    observed = Counter(leading_digits)

    # Chi-squared test against Benford's distribution
    chi2 = 0.0
    for d in range(1, 10):
        expected_count = BENFORD_EXPECTED[d] * n
        obs_count = observed.get(d, 0)
        chi2 += (obs_count - expected_count) ** 2 / expected_count

    # 8 degrees of freedom (digits 1-9, minus 1)
    p_value = 1.0 - stats.chi2.cdf(chi2, df=8)

    # Significant deviation from Benford's → suspicious
    is_suspicious = p_value < config.T18_CHI_SQUARED_PVALUE

    if is_suspicious:
        yes_vol = sum(b.amount for b in bets if b.side == "YES")
        no_vol = sum(b.amount for b in bets if b.side == "NO")
        total_vol = yes_vol + no_vol
        signal = (yes_vol - no_vol) / total_vol if total_vol > 0 else 0.0
        confidence = 1.0 - p_value
    else:
        signal = 0.0
        confidence = 0.1

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "chi2": chi2,
            "p_value": p_value,
            "is_suspicious": is_suspicious,
            "observed_distribution": dict(observed),
            "n": n,
        },
    )


# ---------------------------------------------------------------------------
# T19 — Z-Score Outlier Detection
# ---------------------------------------------------------------------------
@register("T19", "T", "Z-score outlier detection on bet amounts")
def t19_zscore_outlier(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Flag bets with z-score > 2.5 as statistical outliers.
    Cross-reference with wallet rationality to determine if they're sharp or noise."""

    if len(bets) < 5:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    amounts = np.array([b.amount for b in bets])
    mean_amt = float(np.mean(amounts))
    std_amt = float(np.std(amounts))

    if std_amt == 0:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    outlier_yes_vol = 0.0
    outlier_no_vol = 0.0
    outlier_count = 0

    for b in bets:
        z = abs(b.amount - mean_amt) / std_amt
        if z > config.T19_ZSCORE_THRESHOLD:
            outlier_count += 1
            w = wallets.get(b.wallet)
            rationality = w.rationality_score if w else 0.5

            # High rationality outlier = sharp money signal
            # Low rationality outlier = noise / emotional big bet
            weight = b.amount * rationality
            if b.side == "YES":
                outlier_yes_vol += weight
            else:
                outlier_no_vol += weight

    total = outlier_yes_vol + outlier_no_vol
    signal = (outlier_yes_vol - outlier_no_vol) / total if total > 0 else 0.0
    confidence = min(1.0, outlier_count / 5) if outlier_count > 0 else 0.0

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "outlier_count": outlier_count,
            "mean_amount": mean_amt,
            "std_amount": std_amt,
            "threshold": config.T19_ZSCORE_THRESHOLD,
        },
    )
