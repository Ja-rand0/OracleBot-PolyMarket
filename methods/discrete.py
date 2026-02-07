"""D5-D9: Discrete math methods."""
from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np

import config
from data.models import Bet, Market, MethodResult, Wallet
from methods import register

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D5 — Vacuous Truth / Implication Logic
# ---------------------------------------------------------------------------
@register("D5", "D", "Vacuous truth / implication logic")
def d5_vacuous_truth(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Identify markets where the structure makes one outcome near-certain.

    Uses current odds as a proxy: if odds are extreme (>0.95 or <0.05),
    the antecedent condition is effectively decided and the market is
    'vacuously safe' on that side.
    """
    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    # Use median odds as the 'market consensus'
    odds_vals = [b.odds for b in bets if 0 < b.odds < 1]
    if not odds_vals:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    median_odds = float(np.median(odds_vals))

    # Vacuously safe: if the implied probability is extreme, the market is
    # structurally skewed toward one outcome
    if median_odds >= 0.95:
        # YES is near-certain
        signal = 1.0
        confidence = min(1.0, (median_odds - 0.90) / 0.10)
    elif median_odds <= 0.05:
        # NO is near-certain
        signal = -1.0
        confidence = min(1.0, (0.10 - median_odds) / 0.10)
    else:
        signal = 0.0
        confidence = 0.0

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={"median_odds": median_odds},
    )


# ---------------------------------------------------------------------------
# D6 — Graph Theory Wallet Mapping (PageRank)
# ---------------------------------------------------------------------------
@register("D6", "D", "Graph theory wallet mapping (PageRank)")
def d6_pagerank(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Build a directed graph of wallet interactions and weight signal by PageRank."""

    try:
        import networkx as nx
    except ImportError:
        log.warning("networkx not installed — D6 skipped")
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "missing networkx"})

    if len(bets) < 5:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    # Build a directed graph: temporal edges (wallet that bets first → wallet
    # that bets the same side shortly after, suggesting copy-trading / influence)
    G = nx.DiGraph()
    sorted_bets = sorted(bets, key=lambda b: b.timestamp)

    for i, b1 in enumerate(sorted_bets):
        for j in range(i + 1, min(i + 50, len(sorted_bets))):
            b2 = sorted_bets[j]
            delta = (b2.timestamp - b1.timestamp).total_seconds()
            if delta > 600:  # 10 minute window
                break
            if b1.wallet != b2.wallet and b1.side == b2.side:
                if G.has_edge(b1.wallet, b2.wallet):
                    G[b1.wallet][b2.wallet]["weight"] += 1
                else:
                    G.add_edge(b1.wallet, b2.wallet, weight=1)

    if G.number_of_nodes() < 3:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    pr = nx.pagerank(G, weight="weight")

    # Weight bets by their wallet's PageRank
    yes_score = 0.0
    no_score = 0.0
    for b in bets:
        rank = pr.get(b.wallet, 0.0)
        if b.side == "YES":
            yes_score += b.amount * rank
        else:
            no_score += b.amount * rank

    total = yes_score + no_score
    signal = (yes_score - no_score) / total if total > 0 else 0.0
    confidence = min(1.0, G.number_of_nodes() / 20)

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "top_wallets": sorted(pr.items(), key=lambda x: -x[1])[:5],
        },
    )


# ---------------------------------------------------------------------------
# D7 — Pigeonhole Principle Noise Filtering
# ---------------------------------------------------------------------------
@register("D7", "D", "Pigeonhole principle noise filtering")
def d7_pigeonhole(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """If too many wallets appear to have 'insider' info, most are just lucky."""

    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    # Count wallets with high win rates on this market's side
    # (using global win rates as proxy for track record)
    qualified = {
        addr: w for addr, w in wallets.items()
        if w.total_bets >= config.S1_MIN_RESOLVED_BETS
    }

    sharp_count = sum(1 for w in qualified.values() if w.win_rate > 0.65)

    # Estimate max plausible insiders: sqrt of total active wallets
    active_wallets = len({b.wallet for b in bets})
    max_insiders = max(1, int(np.sqrt(active_wallets)))

    if sharp_count <= max_insiders:
        # Genuine signal — not too many 'sharp' bettors
        noise_ratio = 0.0
    else:
        # Too many — apply pigeonhole discount
        noise_ratio = 1.0 - (max_insiders / sharp_count)

    # Signal from all bets, discounted by noise
    yes_vol = sum(b.amount for b in bets if b.side == "YES")
    no_vol = sum(b.amount for b in bets if b.side == "NO")
    total = yes_vol + no_vol
    raw_signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    signal = raw_signal * (1.0 - noise_ratio)
    confidence = 1.0 - noise_ratio

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "sharp_count": sharp_count,
            "max_insiders": max_insiders,
            "noise_ratio": noise_ratio,
            "active_wallets": active_wallets,
        },
    )


# ---------------------------------------------------------------------------
# D8 — Boolean SAT Market Structure
# ---------------------------------------------------------------------------
@register("D8", "D", "Boolean SAT market structure analysis")
def d8_boolean_sat(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Analyse multi-condition market structure.

    For simple YES/NO markets: check if bet distribution structurally
    favours one side (>80% of volume on one side).
    """
    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    yes_count = sum(1 for b in bets if b.side == "YES")
    no_count = sum(1 for b in bets if b.side == "NO")
    total = yes_count + no_count

    if total == 0:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    yes_ratio = yes_count / total

    # If 80%+ of bets favour one side, the structure itself is skewed
    if yes_ratio >= 0.80:
        signal = 1.0
        confidence = min(1.0, (yes_ratio - 0.70) / 0.20)
    elif yes_ratio <= 0.20:
        signal = -1.0
        confidence = min(1.0, (0.30 - yes_ratio) / 0.20)
    else:
        signal = (yes_ratio - 0.5) * 2  # linear mapping to -1..1
        confidence = 0.2

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={"yes_ratio": yes_ratio, "yes_count": yes_count, "no_count": no_count},
    )


# ---------------------------------------------------------------------------
# D9 — Set Partitioning (Clean vs Noise)
# ---------------------------------------------------------------------------
@register("D9", "D", "Set partitioning — clean vs noise separation")
def d9_set_partition(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Master filter: separate emotional (E) from clean (S = U \\ E) bets.

    This method uses wallet rationality scores to partition bets.
    The emotion ratio |E|/|U| is itself a signal about market exploitability.
    """
    if not bets:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    emotional_bets: list[Bet] = []
    clean_bets: list[Bet] = []

    for b in bets:
        w = wallets.get(b.wallet)
        # Wallets with low rationality scores are 'emotional'
        if w and w.rationality_score < 0.4:
            emotional_bets.append(b)
        else:
            clean_bets.append(b)

    emotion_ratio = len(emotional_bets) / len(bets) if bets else 0.0

    # Signal from clean bets only
    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    # Higher emotion ratio → market is potentially more exploitable → higher confidence
    confidence = min(1.0, emotion_ratio + 0.2)

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=clean_bets,
        metadata={
            "total_bets": len(bets),
            "emotional_bets": len(emotional_bets),
            "clean_bets": len(clean_bets),
            "emotion_ratio": emotion_ratio,
        },
    )
