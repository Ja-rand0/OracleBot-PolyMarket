"""E10-E16: Emotional bias filter methods."""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import timedelta

import numpy as np

import config
from data.models import Bet, Market, MethodResult, Wallet
from methods import register

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# E10 — Hometown / Loyalty Bias Detection
# ---------------------------------------------------------------------------
@register("E10", "E", "Hometown/loyalty bias detection")
def e10_loyalty_bias(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Detect wallets that consistently bet one side regardless of odds."""

    # Group bets by wallet
    wallet_bets: dict[str, list[Bet]] = defaultdict(list)
    for b in bets:
        wallet_bets[b.wallet].append(b)

    emotional_wallets: set[str] = set()

    for addr, wbets in wallet_bets.items():
        if len(wbets) < config.E10_MIN_MARKETS:
            continue

        yes_count = sum(1 for b in wbets if b.side == "YES")
        total = len(wbets)
        ratio = max(yes_count / total, 1 - yes_count / total)

        if ratio >= config.E10_CONSISTENCY_THRESHOLD:
            emotional_wallets.add(addr)

    # Filter
    clean_bets = [b for b in bets if b.wallet not in emotional_wallets]
    emotional_bets = [b for b in bets if b.wallet in emotional_wallets]

    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    loyal_volume = sum(b.amount for b in emotional_bets)
    total_volume = sum(b.amount for b in bets)
    confidence = max(0.1, min(1.0, (loyal_volume / total_volume) * 2)) if total_volume > 0 else 0.1

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=clean_bets,
        metadata={
            "emotional_wallets": len(emotional_wallets),
            "bets_filtered": len(emotional_bets),
            "loyal_volume_fraction": loyal_volume / total_volume if total_volume > 0 else 0.0,
        },
    )


# ---------------------------------------------------------------------------
# E11 — Recency Bias Detection
# ---------------------------------------------------------------------------
@register("E11", "E", "Recency bias detection")
def e11_recency_bias(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Detect bets that follow recent outcomes blindly.

    Approximation: if a burst of same-side bets happens at the start of
    a market (people extrapolating from a related recent outcome), those
    are recency-biased.
    """
    if len(bets) < 5:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    sorted_bets = sorted(bets, key=lambda b: b.timestamp)

    # Look at the first 20% of bets
    early_cutoff = max(1, len(sorted_bets) // 5)
    early_bets = sorted_bets[:early_cutoff]
    late_bets = sorted_bets[early_cutoff:]

    early_yes = sum(1 for b in early_bets if b.side == "YES")
    early_total = len(early_bets)
    early_ratio = early_yes / early_total if early_total > 0 else 0.5

    late_yes = sum(1 for b in late_bets if b.side == "YES")
    late_total = len(late_bets)
    late_ratio = late_yes / late_total if late_total > 0 else 0.5

    # If early bets are heavily skewed vs later bets → recency bias in early bets
    skew = abs(early_ratio - late_ratio)

    if skew > 0.3:
        # Early bets are biased — filter wallets that only bet early
        early_wallets = {b.wallet for b in early_bets}
        late_wallets = {b.wallet for b in late_bets}
        only_early = early_wallets - late_wallets

        clean_bets = [b for b in bets if b.wallet not in only_early]
    else:
        clean_bets = bets

    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    return MethodResult(
        signal=signal,
        confidence=max(0.1, min(1.0, skew * 2)),
        filtered_bets=clean_bets,
        metadata={
            "early_ratio": early_ratio,
            "late_ratio": late_ratio,
            "skew": skew,
            "bets_filtered": len(bets) - len(clean_bets),
        },
    )


# ---------------------------------------------------------------------------
# E12 — Revenge Betting Patterns
# ---------------------------------------------------------------------------
@register("E12", "E", "Revenge betting patterns")
def e12_revenge_betting(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Detect wallets that increase position size after losses (tilt/revenge)."""

    wallet_bets: dict[str, list[Bet]] = defaultdict(list)
    for b in bets:
        wallet_bets[b.wallet].append(b)

    revenge_wallets: set[str] = set()

    for addr, wbets in wallet_bets.items():
        if len(wbets) < 2:
            continue

        sorted_wb = sorted(wbets, key=lambda b: b.timestamp)

        for i in range(1, len(sorted_wb)):
            prev = sorted_wb[i - 1]
            curr = sorted_wb[i]

            time_gap = (curr.timestamp - prev.timestamp).total_seconds() / 3600
            if time_gap > config.E12_WINDOW_HOURS:
                continue

            # Revenge pattern: bet size increases significantly (1.5x+)
            if curr.amount >= prev.amount * 1.5 and curr.amount > 100:
                revenge_wallets.add(addr)
                break

    clean_bets = [b for b in bets if b.wallet not in revenge_wallets]

    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    return MethodResult(
        signal=signal,
        confidence=min(1.0, len(revenge_wallets) / 5) if revenge_wallets else 0.1,
        filtered_bets=clean_bets,
        metadata={
            "revenge_wallets": len(revenge_wallets),
            "bets_filtered": len(bets) - len(clean_bets),
        },
    )


# ---------------------------------------------------------------------------
# E13 — Hype / Media Cycle Correlation
# ---------------------------------------------------------------------------
@register("E13", "E", "Hype/media cycle correlation")
def e13_hype_detection(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Detect bet volume spikes (3x+) that suggest hype-driven activity."""

    if len(bets) < 10:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    sorted_bets = sorted(bets, key=lambda b: b.timestamp)

    # Bucket bets into hourly windows
    hourly_volume: dict[int, float] = defaultdict(float)
    hourly_bets: dict[int, list[Bet]] = defaultdict(list)

    first_ts = sorted_bets[0].timestamp
    for b in sorted_bets:
        hour = int((b.timestamp - first_ts).total_seconds() // 3600)
        hourly_volume[hour] += b.amount
        hourly_bets[hour].append(b)

    if len(hourly_volume) < 3:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    volumes = list(hourly_volume.values())
    median_vol = float(np.median(volumes))

    if median_vol == 0:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    # Flag spike windows
    spike_bets: list[Bet] = []
    for hour, vol in hourly_volume.items():
        if vol >= median_vol * config.E13_VOLUME_SPIKE_MULTIPLIER:
            spike_bets.extend(hourly_bets[hour])

    spike_ids = {id(b) for b in spike_bets}
    clean_bets = [b for b in bets if id(b) not in spike_ids]

    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    return MethodResult(
        signal=signal,
        confidence=min(1.0, len(spike_bets) / len(bets)) if spike_bets else 0.1,
        filtered_bets=clean_bets,
        metadata={
            "spike_bets": len(spike_bets),
            "median_hourly_volume": median_vol,
            "spike_hours": sum(1 for v in volumes if v >= median_vol * config.E13_VOLUME_SPIKE_MULTIPLIER),
        },
    )


# ---------------------------------------------------------------------------
# E14 — Odds Sensitivity Scoring
# ---------------------------------------------------------------------------
@register("E14", "E", "Odds sensitivity scoring")
def e14_odds_sensitivity(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Emotional bettors don't adjust size with odds. Filter them."""

    wallet_bets: dict[str, list[Bet]] = defaultdict(list)
    for b in bets:
        wallet_bets[b.wallet].append(b)

    emotional_wallets: set[str] = set()

    for addr, wbets in wallet_bets.items():
        if len(wbets) < 3:
            continue

        amounts = [b.amount for b in wbets]
        odds = [b.odds for b in wbets]

        # Correlation between bet size and odds
        if np.std(amounts) == 0 or np.std(odds) == 0:
            emotional_wallets.add(addr)
            continue

        corr = float(np.corrcoef(amounts, odds)[0, 1])

        # Low correlation = emotional (they bet same size regardless)
        if abs(corr) < config.E14_LOW_CORRELATION_THRESHOLD:
            emotional_wallets.add(addr)

    clean_bets = [b for b in bets if b.wallet not in emotional_wallets]

    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    return MethodResult(
        signal=signal,
        confidence=min(1.0, len(emotional_wallets) / 10) if emotional_wallets else 0.1,
        filtered_bets=clean_bets,
        metadata={
            "emotional_wallets": len(emotional_wallets),
            "bets_filtered": len(bets) - len(clean_bets),
        },
    )


# ---------------------------------------------------------------------------
# E15 — Position Sizing Precision
# ---------------------------------------------------------------------------
@register("E15", "E", "Position sizing precision")
def e15_round_number(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Emotional bets tend to be round numbers ($50, $100, $500).
    Sharp money is precisely sized."""

    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    wallet_round_ratio: dict[str, float] = {}
    wallet_bets: dict[str, list[Bet]] = defaultdict(list)

    for b in bets:
        wallet_bets[b.wallet].append(b)

    emotional_wallets: set[str] = set()

    for addr, wbets in wallet_bets.items():
        if len(wbets) < 2:
            continue

        round_count = sum(
            1 for b in wbets
            if b.amount >= config.E15_ROUND_DIVISOR
            and b.amount % config.E15_ROUND_DIVISOR == 0
        )
        ratio = round_count / len(wbets)
        wallet_round_ratio[addr] = ratio

        if ratio > 0.7:
            emotional_wallets.add(addr)

    clean_bets = [b for b in bets if b.wallet not in emotional_wallets]

    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    return MethodResult(
        signal=signal,
        confidence=min(1.0, len(emotional_wallets) / 10) if emotional_wallets else 0.1,
        filtered_bets=clean_bets,
        metadata={
            "emotional_wallets": len(emotional_wallets),
            "bets_filtered": len(bets) - len(clean_bets),
        },
    )


# ---------------------------------------------------------------------------
# E16 — Bipartite Graph Pruning
# ---------------------------------------------------------------------------
@register("E16", "E", "Bipartite graph pruning (KL divergence)")
def e16_bipartite_pruning(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Prune wallets whose bet distribution is heavily skewed (high KL divergence)."""

    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    wallet_bets: dict[str, list[Bet]] = defaultdict(list)
    for b in bets:
        wallet_bets[b.wallet].append(b)

    emotional_wallets: set[str] = set()

    for addr, wbets in wallet_bets.items():
        if len(wbets) < 3:
            continue

        yes_count = sum(1 for b in wbets if b.side == "YES")
        no_count = len(wbets) - yes_count
        total = len(wbets)

        # KL divergence from uniform (0.5, 0.5)
        p_yes = max(yes_count / total, 1e-10)
        p_no = max(no_count / total, 1e-10)
        kl = p_yes * math.log(p_yes / 0.5) + p_no * math.log(p_no / 0.5)

        if kl > config.E16_KL_THRESHOLD:
            emotional_wallets.add(addr)

    clean_bets = [b for b in bets if b.wallet not in emotional_wallets]

    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total_vol = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total_vol if total_vol > 0 else 0.0

    return MethodResult(
        signal=signal,
        confidence=min(1.0, len(emotional_wallets) / 10) if emotional_wallets else 0.1,
        filtered_bets=clean_bets,
        metadata={
            "emotional_wallets": len(emotional_wallets),
            "bets_filtered": len(bets) - len(clean_bets),
        },
    )
