import pytest
from datetime import datetime, timedelta, timezone
from data.models import Market, Bet, ComboResults
from engine.fitness import calculate_fitness
from engine.backtest import split_holdout, backtest_combo
from tests.conftest import make_bet, make_wallet
import config


# --- fitness ---

def test_fitness_formula():
    cr = ComboResults(combo_id="X", methods_used=["E15"], accuracy=1.0,
                      edge_vs_market=1.0, false_positive_rate=0.0,
                      complexity=1, tested_at=datetime.now(timezone.utc).replace(tzinfo=None))
    cr.fitness_score = calculate_fitness(cr)
    expected = 1.0 * 0.35 + 1.0 * 0.35 - 0.0 * 0.20 - (1 / config.TOTAL_METHODS) * 0.10
    assert cr.fitness_score == pytest.approx(expected, abs=0.001)

def test_fitness_complexity_penalty():
    def make_cr(complexity):
        c = ComboResults(combo_id="X", methods_used=[], accuracy=0.6,
                         edge_vs_market=0.1, false_positive_rate=0.1,
                         complexity=complexity, tested_at=datetime.now(timezone.utc).replace(tzinfo=None))
        c.fitness_score = calculate_fitness(c)
        return c
    assert make_cr(1).fitness_score > make_cr(5).fitness_score


# --- split_holdout ---

def _make_market(i):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Market(id=str(i), title="", description="",
                  end_date=now, resolved=True,
                  created_at=now - timedelta(days=100 - i))

def test_split_holdout_sizes():
    markets = [_make_market(i) for i in range(10)]
    train, holdout = split_holdout(markets, 0.20)
    assert len(train) == 8
    assert len(holdout) == 2

def test_split_holdout_temporal_order():
    markets = [_make_market(i) for i in range(10)]
    train, holdout = split_holdout(markets, 0.20)
    assert max(m.created_at for m in train) <= min(m.created_at for m in holdout)

def test_split_holdout_empty():
    train, holdout = split_holdout([], 0.20)
    assert train == [] and holdout == []


# --- backtest_combo ---

def test_backtest_combo_d5_correct_prediction():
    # Near-certain YES market (median odds 0.97) resolved YES → D5 predicts correctly.
    # Bets placed at offset_hours=240 (10 days ago) sit inside the 70% cutoff
    # of a 14-day market (cutoff = created_at + 9.8d = now - 4.2d; 10d ago is before that).
    market = Market(
        id="m1", title="Near certain YES", description="",
        end_date=datetime.now(timezone.utc).replace(tzinfo=None), resolved=True, outcome="YES",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=14),
    )
    bets = [make_bet(market_id="m1", wallet=f"W{i}", side="YES",
                     odds=0.97, offset_hours=240 + i) for i in range(5)]
    result = backtest_combo(["D5"], [market], {"m1": bets}, {})
    assert result.accuracy == pytest.approx(1.0)
    assert result.fitness_score > 0.0
