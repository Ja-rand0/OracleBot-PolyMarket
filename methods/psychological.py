"""P20-P24: Psychological / sociological signal methods."""
from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from datetime import timedelta

import numpy as np

import config
from data.models import Bet, Market, MethodResult, Wallet
from methods import register

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P20 — Nash Equilibrium Deviation
# ---------------------------------------------------------------------------
@register("P20", "P", "Nash equilibrium deviation")
def p20_nash_deviation(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Measure deviation of current odds from theoretical Nash equilibrium.

    In a binary prediction market the Nash equilibrium price equals the
    consensus probability.  We approximate equilibrium as the volume-weighted
    average price, then compare to the latest marginal price.  A large
    gap suggests information asymmetry.
    """
    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    # Volume-weighted average price (proxy for equilibrium)
    total_vol = sum(b.amount for b in bets)
    if total_vol == 0:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    vwap = sum(b.odds * b.amount for b in bets) / total_vol

    # Latest marginal price (last N bets)
    sorted_bets = sorted(bets, key=lambda b: b.timestamp)
    recent = sorted_bets[-min(10, len(sorted_bets)):]
    recent_price = float(np.mean([b.odds for b in recent]))

    deviation = recent_price - vwap

    if abs(deviation) > config.P20_DEVIATION_THRESHOLD:
        # Significant deviation — the direction of deviation suggests
        # which side has private information
        signal = max(-1.0, min(1.0, deviation * 3))
        confidence = min(1.0, abs(deviation) / 0.3)
    else:
        signal = 0.0
        confidence = 0.1

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "vwap": vwap,
            "recent_price": recent_price,
            "deviation": deviation,
        },
    )


# ---------------------------------------------------------------------------
# P21 — Prospect Theory Exploitation
# ---------------------------------------------------------------------------
@register("P21", "P", "Prospect theory exploitation")
def p21_prospect_theory(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Exploit Kahneman/Tversky probability weighting:
    - Low-probability events (<10%) are over-bet → market overprices YES
    - High-probability events (>90%) are under-bet → market underprices YES

    The probability weighting function: w(p) = p^γ / (p^γ + (1-p)^γ)^(1/γ)
    with γ ≈ 0.61 (Tversky & Kahneman 1992).
    """
    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    # Current implied probability (median odds)
    odds_vals = [b.odds for b in bets if 0 < b.odds < 1]
    if not odds_vals:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    implied_prob = float(np.median(odds_vals))

    # Prospect theory weighting function
    gamma = 0.61
    def weight(p: float) -> float:
        if p <= 0 or p >= 1:
            return p
        pg = p ** gamma
        return pg / (pg + (1 - p) ** gamma) ** (1 / gamma)

    weighted_prob = weight(implied_prob)
    mispricing = implied_prob - weighted_prob

    if implied_prob < config.P21_LOW_PROB:
        # Low-prob event: emotional money over-bets YES
        # True probability is likely lower → signal NO
        signal = -abs(mispricing) * 5
        confidence = min(1.0, abs(mispricing) * 10)
    elif implied_prob > config.P21_HIGH_PROB:
        # High-prob event: emotional money under-bets YES
        # True probability is likely higher → signal YES
        signal = abs(mispricing) * 5
        confidence = min(1.0, abs(mispricing) * 10)
    else:
        signal = -mispricing * 2
        confidence = min(1.0, abs(mispricing) * 5)

    signal = max(-1.0, min(1.0, signal))

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "implied_prob": implied_prob,
            "weighted_prob": weighted_prob,
            "mispricing": mispricing,
        },
    )


# ---------------------------------------------------------------------------
# P22 — Herding Behavior Detection
# ---------------------------------------------------------------------------
@register("P22", "P", "Herding behavior detection")
def p22_herding(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Measure temporal clustering of same-side bets.
    Herding bets are partially discounted (the herd is sometimes right)."""

    if len(bets) < config.P22_MIN_HERD_SIZE:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    sorted_bets = sorted(bets, key=lambda b: b.timestamp)
    window = timedelta(minutes=config.P22_TIME_WINDOW_MINUTES)

    # Sliding window O(n): two-pointer with deque tracking window contents
    max_cluster_size = 0
    max_cluster_side = "YES"
    yes_in_window = 0
    no_in_window = 0
    left = 0

    for right, bet in enumerate(sorted_bets):
        if bet.side == "YES":
            yes_in_window += 1
        else:
            no_in_window += 1

        # Shrink window from the left until it fits
        while sorted_bets[left].timestamp < bet.timestamp - window:
            if sorted_bets[left].side == "YES":
                yes_in_window -= 1
            else:
                no_in_window -= 1
            left += 1

        cluster_size = max(yes_in_window, no_in_window)
        if cluster_size > max_cluster_size:
            max_cluster_size = cluster_size
            max_cluster_side = "YES" if yes_in_window > no_in_window else "NO"

    # Independence test: expected cluster under random betting
    total_yes = sum(1 for b in bets if b.side == "YES")
    total_no = len(bets) - total_yes
    p_same = (total_yes / len(bets)) ** 2 + (total_no / len(bets)) ** 2
    # Scale expected cluster by actual betting rate over market lifespan
    if len(sorted_bets) >= 2:
        span_minutes = (sorted_bets[-1].timestamp - sorted_bets[0].timestamp).total_seconds() / 60
        num_windows = max(1.0, span_minutes / config.P22_TIME_WINDOW_MINUTES)
        same_side_total = total_yes if max_cluster_side == "YES" else total_no
        expected_cluster = max(1, int(same_side_total / num_windows))
        avg_bets_per_window = len(bets) / num_windows
    else:
        expected_cluster = max(1, int(p_same * config.P22_MIN_HERD_SIZE))
        avg_bets_per_window = 1.0

    independence_score = expected_cluster / max(max_cluster_size, 1)
    # Herding if cluster is more than 3x the average bets per window (adaptive to bet density)
    is_herding = max_cluster_size > 3 * max(1.0, avg_bets_per_window)

    # Partially discount herding direction
    discount = 0.5 if is_herding else 1.0

    yes_vol = sum(b.amount for b in bets if b.side == "YES")
    no_vol = sum(b.amount for b in bets if b.side == "NO")
    total = yes_vol + no_vol
    raw_signal = (yes_vol - no_vol) / total if total > 0 else 0.0
    signal = raw_signal * discount

    return MethodResult(
        signal=signal,
        confidence=min(1.0, 1.0 - independence_score) if is_herding else 0.0,
        filtered_bets=bets,
        metadata={
            "max_cluster_size": max_cluster_size,
            "max_cluster_side": max_cluster_side,
            "expected_cluster": expected_cluster,
            "independence_score": independence_score,
            "is_herding": is_herding,
        },
    )


# ---------------------------------------------------------------------------
# P23 — Anchoring Bias Tracking
# ---------------------------------------------------------------------------
@register("P23", "P", "Anchoring bias tracking")
def p23_anchoring(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Identify the anchor (first large bet) and measure how much the market
    clusters around its implied probability. High anchoring = exploitable gap."""

    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    sorted_bets = sorted(bets, key=lambda b: b.timestamp)

    # Find the anchor: first bet above threshold
    anchor = None
    for b in sorted_bets:
        if b.amount >= config.P23_ANCHOR_MIN_AMOUNT:
            anchor = b
            break

    if anchor is None:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "no anchor found"})

    anchor_odds = anchor.odds

    # Measure clustering around anchor odds
    subsequent = [b for b in sorted_bets if b.timestamp > anchor.timestamp]
    if not subsequent:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    diffs = [abs(b.odds - anchor_odds) for b in subsequent]
    mean_diff = float(np.mean(diffs))

    # Strong anchoring = low mean diff from anchor price
    anchoring_strength = max(0.0, 1.0 - mean_diff * 5)

    if anchoring_strength > 0.7:
        # Market is heavily anchored — the anchor might be wrong
        # Signal opposite to anchor if later rational bets disagree
        late_bets = subsequent[-(len(subsequent) // 4):]
        late_yes = sum(b.amount for b in late_bets if b.side == "YES")
        late_no = sum(b.amount for b in late_bets if b.side == "NO")
        late_total = late_yes + late_no
        if late_total > 0:
            late_signal = (late_yes - late_no) / late_total
            anchor_signal = 1.0 if anchor.side == "YES" else -1.0
            # If late money disagrees with anchor, there's an exploitable gap
            signal = late_signal
        else:
            signal = 0.0
    else:
        signal = 0.0

    return MethodResult(
        signal=signal,
        confidence=anchoring_strength * 0.8,
        filtered_bets=bets,
        metadata={
            "anchor_wallet": anchor.wallet[:10],
            "anchor_odds": anchor_odds,
            "anchor_amount": anchor.amount,
            "anchoring_strength": anchoring_strength,
            "mean_diff_from_anchor": mean_diff,
        },
    )


# ---------------------------------------------------------------------------
# P24 — Wisdom vs Madness Ratio
# ---------------------------------------------------------------------------
@register("P24", "P", "Wisdom vs madness ratio")
def p24_wisdom_madness(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Meta-signal: what percentage of bets are emotional?
    High ratio = market is inefficient and exploitable.
    This tells you WHICH markets to focus on, not which side to bet."""

    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    emotional_count = 0
    for b in bets:
        w = wallets.get(b.wallet)
        if w and w.rationality_score < 0.4:
            emotional_count += 1

    ratio = emotional_count / len(bets)

    # Signal from all bets
    yes_vol = sum(b.amount for b in bets if b.side == "YES")
    no_vol = sum(b.amount for b in bets if b.side == "NO")
    total = yes_vol + no_vol
    raw_signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    if ratio > config.P24_HIGH_RATIO:
        # Madness of crowds — market is exploitable, trust the signal more
        signal = raw_signal
        confidence = min(1.0, ratio)
    elif ratio < config.P24_LOW_RATIO:
        # Wisdom of crowds — market is efficient, hard to beat
        signal = raw_signal * 0.3  # dampen
        confidence = 0.2
    else:
        signal = raw_signal * 0.6
        confidence = 0.4

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "emotion_ratio": ratio,
            "emotional_bets": emotional_count,
            "total_bets": len(bets),
            "regime": "madness" if ratio > config.P24_HIGH_RATIO
                      else "wisdom" if ratio < config.P24_LOW_RATIO
                      else "mixed",
        },
    )
