"""
engine/relationships.py — Persist wallet relationship signals from S3.

Runs S3 (coordination clustering) on active markets and writes detected wallet
pairs to the wallet_relationships table.

Called once per analysis cycle after the combinator finishes.
"""

import logging
from itertools import combinations

from data import db
from data.models import WalletRelationship
from methods.suspicious import s3_coordination_clustering

log = logging.getLogger("relationships")


def persist_graph_relationships(conn, markets, bets_by_market: dict, wallets: dict) -> None:
    """Run S3 on active markets and persist wallet relationships to DB."""
    rels: list[WalletRelationship] = []

    for market in markets:
        bets = bets_by_market.get(market.id)
        if not bets or len(bets) < 10:
            continue

        # Per-market wallet dict (never pass full 140k+ wallet dict to methods)
        market_wallets = {b.wallet: wallets[b.wallet] for b in bets if b.wallet in wallets}

        # --- S3: Coordination Clustering ---
        try:
            s3_result = s3_coordination_clustering(market, bets, market_wallets)
            cluster_members = s3_result.metadata.get("cluster_members", {})
            for members in cluster_members.values():
                if len(members) < 2:
                    continue
                confidence = min(1.0, len(members) / 10)
                for wallet_a, wallet_b in combinations(sorted(members), 2):
                    rels.append(WalletRelationship(
                        wallet_a=wallet_a,
                        wallet_b=wallet_b,
                        relationship_type="coordination",
                        confidence=confidence,
                    ))
        except Exception:
            log.debug("S3 failed for market %s", market.id, exc_info=True)

    if not rels:
        log.info("No wallet relationships detected this cycle")
        return

    db.upsert_relationships_batch(conn, rels)
    log.info("Persisted %d wallet relationships (coordination)", len(rels))
