"""Fitness / scoring function for method combo evaluation."""
from __future__ import annotations

import config
from data.models import ComboResults


def calculate_fitness(cr: ComboResults) -> float:
    """Score a method combination. Higher is better.

    Components:
        accuracy          (weight 0.35) — % correct on resolved markets
        edge_vs_market    (weight 0.35) — improvement over raw market odds
        false_positive    (weight 0.20) — penalty for flagging wrong bets
        complexity        (weight 0.10) — penalty for using too many methods
    """
    fitness = (
        cr.accuracy * config.FITNESS_W_ACCURACY
        + cr.edge_vs_market * config.FITNESS_W_EDGE
        - cr.false_positive_rate * config.FITNESS_W_FALSE_POS
        - (cr.complexity / 24) * config.FITNESS_W_COMPLEXITY
    )
    return fitness
