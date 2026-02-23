"""
Method registry — all 28 analysis methods registered here.

Each method is a callable with signature:
    (market: Market, bets: list[Bet], wallets: dict[str, Wallet]) -> MethodResult

Methods are grouped by category:
    S  (S1-S4)   — Suspicious wallet detection
    D  (D5-D9)   — Discrete math methods
    E  (E10-E16) — Emotional bias filters
    T  (T17-T19) — Statistical analysis
    P  (P20-P24) — Psychological / sociological signals
    M  (M25-M28) — Markov chain / temporal transition analysis
"""
from __future__ import annotations

from typing import Callable

from data.models import Bet, Market, MethodResult, Wallet

MethodFn = Callable[[Market, list[Bet], dict[str, Wallet]], MethodResult]

# Registry: method_id -> (function, category, description)
METHODS: dict[str, tuple[MethodFn, str, str]] = {}

CATEGORIES = {
    "S": ["S1", "S3", "S4"],        # S2 removed: interchangeable with S1, subadditive
    "D": ["D5", "D7", "D8", "D9"],  # D6 removed: never top-25, adds graph overhead
    "E": ["E10", "E11", "E12", "E13", "E14", "E15", "E16"],
    "T": ["T17", "T18", "T19"],
    "P": ["P20", "P21", "P22", "P23", "P24"],
    "M": ["M26", "M27", "M28"],     # M25 removed: actively hurts M26+M28 combos
}


def register(method_id: str, category: str, description: str):
    """Decorator to register a method in the global registry."""
    def decorator(fn: MethodFn) -> MethodFn:
        METHODS[method_id] = (fn, category, description)
        return fn
    return decorator


def get_method(method_id: str) -> MethodFn:
    return METHODS[method_id][0]


def get_methods_by_category(category: str) -> list[str]:
    return [mid for mid, (_, cat, _) in METHODS.items() if cat == category]


def get_all_method_ids() -> list[str]:
    return list(METHODS.keys())


# Import all method modules to trigger registration
from methods import suspicious    # noqa: F401, E402
from methods import discrete      # noqa: F401, E402
from methods import emotional     # noqa: F401, E402
from methods import statistical   # noqa: F401, E402
from methods import psychological # noqa: F401, E402
from methods import markov       # noqa: F401, E402
