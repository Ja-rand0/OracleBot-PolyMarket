"""
engine/relationships.py — Persist wallet relationship signals from S3 and D6.

Runs S3 (coordination clustering) and D6 (PageRank copy-trading graph) on active
markets and writes detected wallet pairs to the wallet_relationships table.

Called once per analysis cycle after the combinator finishes.
D6 is NOT in CATEGORIES (no combo impact) — imported directly for relationship use only.
"""

import logging
from itertools import combinations

from data import db
from data.models import WalletRelationship
from methods.discrete import d6_pagerank
from methods.suspicious import s3_coordination_clustering

log = logging.getLogger("relationships")


def persist_graph_relationships(conn, markets, bets_by_market: dict, wallets: dict) -> None:
    """Run S3 + D6 on active markets and persist wallet relationships to DB."""
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

        # --- D6: PageRank copy-trading graph ---
        try:
            d6_result = d6_pagerank(market, bets, market_wallets)
            edge_list = d6_result.metadata.get("edge_list", [])
            for src, dst, weight in edge_list:
                confidence = min(1.0, weight / 5)
                wallet_a, wallet_b = tuple(sorted([src, dst]))
                rels.append(WalletRelationship(
                    wallet_a=wallet_a,
                    wallet_b=wallet_b,
                    relationship_type="copy_trading",
                    confidence=confidence,
                ))
        except Exception:
            log.debug("D6 failed for market %s", market.id, exc_info=True)

    if not rels:
        log.info("No wallet relationships detected this cycle")
        return

    coordination_count = sum(1 for r in rels if r.relationship_type == "coordination")
    copy_trading_count = sum(1 for r in rels if r.relationship_type == "copy_trading")

    db.upsert_relationships_batch(conn, rels)
    log.info(
        "Persisted %d wallet relationships (%d coordination, %d copy_trading)",
        len(rels),
        coordination_count,
        copy_trading_count,
    )
