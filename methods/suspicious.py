"""S1-S4: Suspicious wallet detection methods."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

import numpy as np

import config
from data.models import Bet, Market, MethodResult, Wallet
from methods import register

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# S1 — Win Rate Outlier Detection
# ---------------------------------------------------------------------------
@register("S1", "S", "Win rate outlier detection")
def s1_win_rate_outlier(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Flag wallets with win rates > 2σ above the mean.
    Weight their bets higher as a signal."""

    qualified = {
        addr: w for addr, w in wallets.items()
        if w.total_bets >= config.S1_MIN_RESOLVED_BETS
    }

    if len(qualified) < 3:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "insufficient qualified wallets"})

    win_rates = np.array([w.win_rate for w in qualified.values()])
    mean_wr = float(np.mean(win_rates))
    std_wr = float(np.std(win_rates))

    if std_wr == 0:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "zero std dev"})

    threshold = mean_wr + config.S1_STDDEV_THRESHOLD * std_wr
    sharp_wallets = {addr for addr, w in qualified.items() if w.win_rate > threshold}

    if not sharp_wallets:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"sharp_wallets": 0, "threshold": threshold})

    # Aggregate signal: which side do the sharp wallets favour?
    yes_vol = 0.0
    no_vol = 0.0
    for b in bets:
        if b.wallet in sharp_wallets:
            if b.side == "YES":
                yes_vol += b.amount
            else:
                no_vol += b.amount

    total = yes_vol + no_vol
    if total == 0:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"sharp_wallets": len(sharp_wallets)})

    signal = (yes_vol - no_vol) / total  # -1 to +1
    confidence = min(1.0, len(sharp_wallets) / 10)

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "sharp_wallets": len(sharp_wallets),
            "threshold": threshold,
            "mean_wr": mean_wr,
            "std_wr": std_wr,
            "yes_vol": yes_vol,
            "no_vol": no_vol,
        },
    )


# ---------------------------------------------------------------------------
# S3 — Wallet Coordination Clustering
# ---------------------------------------------------------------------------
@register("S3", "S", "Wallet coordination clustering")
def s3_coordination_clustering(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Detect coordinated wallet clusters via temporal co-betting patterns."""

    try:
        import networkx as nx
        from community import community_louvain
    except ImportError:
        log.warning("networkx or python-louvain not installed — S3 skipped")
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "missing dependencies"})

    if len(bets) < 10:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets)

    # Group bets by market_id to find cross-market co-betting
    # For a single-market call, we look at temporal clustering within this market
    window = timedelta(minutes=config.S3_TIME_WINDOW_MINUTES)

    # Sort by timestamp
    sorted_bets = sorted(bets, key=lambda b: b.timestamp)

    # Build co-occurrence edges: wallets betting same side within window
    edges: dict[tuple[str, str], int] = defaultdict(int)
    for i, b1 in enumerate(sorted_bets):
        for j in range(i + 1, len(sorted_bets)):
            b2 = sorted_bets[j]
            if b2.timestamp - b1.timestamp > window:
                break
            if b1.wallet != b2.wallet and b1.side == b2.side:
                pair = tuple(sorted([b1.wallet, b2.wallet]))
                edges[pair] += 1

    # Only keep edges with enough co-occurrences
    strong_edges = {pair: cnt for pair, cnt in edges.items() if cnt >= 2}

    if not strong_edges:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"clusters": 0})

    G = nx.Graph()
    for (a, b), weight in strong_edges.items():
        G.add_edge(a, b, weight=weight)

    if G.number_of_nodes() < config.S3_MIN_CLUSTER_SIZE:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"clusters": 0, "nodes": G.number_of_nodes()})

    partition = community_louvain.best_partition(G)
    clusters: dict[int, list[str]] = defaultdict(list)
    for node, comm in partition.items():
        clusters[comm].append(node)

    suspicious_clusters = {
        cid: members for cid, members in clusters.items()
        if len(members) >= config.S3_MIN_CLUSTER_SIZE
    }

    if not suspicious_clusters:
        return MethodResult(signal=0.0, confidence=0.2, filtered_bets=bets,
                            metadata={"clusters": 0})

    # Signal: direction the largest cluster is betting
    all_suspicious = set()
    for members in suspicious_clusters.values():
        all_suspicious.update(members)

    yes_vol = sum(b.amount for b in bets if b.wallet in all_suspicious and b.side == "YES")
    no_vol = sum(b.amount for b in bets if b.wallet in all_suspicious and b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0
    confidence = min(1.0, len(all_suspicious) / 10)

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "clusters": len(suspicious_clusters),
            "suspicious_wallets": len(all_suspicious),
            "cluster_sizes": [len(m) for m in suspicious_clusters.values()],
            "cluster_members": {str(cid): members for cid, members in suspicious_clusters.items()},
        },
    )


# ---------------------------------------------------------------------------
# S4 — Sandpit / Bait Account Filtering
# ---------------------------------------------------------------------------
@register("S4", "S", "Sandpit/bait account filtering")
def s4_sandpit_filter(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    """Detect and exclude sandpit/bait accounts from the smart money pool.
    Returns filtered_bets with sandpit wallets removed."""

    sandpit_wallets: set[str] = set()

    for addr, w in wallets.items():
        if w.flagged_sandpit:
            sandpit_wallets.add(addr)
            continue

        # Pattern: won big once then consistently loses
        # Approximation: high volume but very low win rate with enough bets
        if (w.total_bets >= config.S4_SANDPIT_MIN_BETS
                and w.win_rate < config.S4_SANDPIT_MAX_WIN_RATE
                and w.total_volume > config.S4_SANDPIT_MIN_VOLUME):
            sandpit_wallets.add(addr)
            continue

        # Pattern: brand new wallet with suspiciously large first bet
        wallet_bets = [b for b in bets if b.wallet == addr]
        if wallet_bets and w.total_bets <= config.S4_NEW_WALLET_MAX_BETS:
            max_bet = max(b.amount for b in wallet_bets)
            if max_bet > config.S4_NEW_WALLET_LARGE_BET:
                sandpit_wallets.add(addr)
                continue

    # Filter out sandpit wallets
    clean_bets = [b for b in bets if b.wallet not in sandpit_wallets]

    # Signal from clean bets
    yes_vol = sum(b.amount for b in clean_bets if b.side == "YES")
    no_vol = sum(b.amount for b in clean_bets if b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0

    return MethodResult(
        signal=signal,
        confidence=0.5 if sandpit_wallets else 0.1,
        filtered_bets=clean_bets,
        metadata={
            "sandpit_wallets": len(sandpit_wallets),
            "bets_removed": len(bets) - len(clean_bets),
        },
    )
