from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Market:
    id: str
    title: str
    description: str
    end_date: datetime
    resolved: bool = False
    outcome: Optional[str] = None  # "YES" or "NO" once resolved
    created_at: datetime = field(default_factory=datetime.utcnow)
    volume: float = 0.0  # total traded volume (not persisted, used for sorting)


@dataclass
class Bet:
    market_id: str
    wallet: str
    side: str           # "YES" or "NO"
    amount: float
    odds: float          # price at time of bet (0.0 to 1.0)
    timestamp: datetime
    id: Optional[int] = None


@dataclass
class Wallet:
    address: str
    first_seen: datetime = field(default_factory=datetime.utcnow)
    total_bets: int = 0
    total_volume: float = 0.0
    win_rate: float = 0.0
    rationality_score: float = 0.0
    flagged_suspicious: bool = False
    flagged_sandpit: bool = False


@dataclass
class WalletRelationship:
    wallet_a: str
    wallet_b: str
    relationship_type: str  # 'coordination', 'funding', 'copy_trading'
    confidence: float


@dataclass
class MethodResult:
    signal: float          # -1.0 (strong NO) to 1.0 (strong YES)
    confidence: float      # 0.0 to 1.0
    filtered_bets: list[Bet] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ComboResults:
    combo_id: str          # e.g. "S1,S2,E14,T17"
    methods_used: list[str] = field(default_factory=list)
    accuracy: float = 0.0
    edge_vs_market: float = 0.0
    false_positive_rate: float = 0.0
    complexity: int = 0
    fitness_score: float = 0.0
    tested_at: datetime = field(default_factory=datetime.utcnow)
