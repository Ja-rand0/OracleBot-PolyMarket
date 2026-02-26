import pytest
from methods.psychological import (
    p20_nash_deviation, p21_prospect_theory,
    p22_herding, p23_anchoring, p24_wisdom_madness,
)
from tests.conftest import make_bet, make_wallet


# --- P20 ---

def test_p20_rising_recent_price_signals_yes(base_market):
    # Old bets: odds=0.40 (VWAP anchored low). Recent 10 bets: odds=0.80.
    # deviation = recent_price - vwap > P20_DEVIATION_THRESHOLD=0.02 → signal > 0.
    old = [make_bet(side="YES", amount=100, odds=0.40, offset_hours=10 - i)
           for i in range(15)]
    recent = [make_bet(side="YES", amount=100, odds=0.80, offset_hours=float(i) * 0.1)
              for i in range(10)]
    result = p20_nash_deviation(base_market, old + recent, {})
    assert result.signal > 0.0
    assert result.confidence > 0.1


def test_p20_stable_price_no_signal(base_market):
    # All bets same odds → deviation = 0 → signal=0, confidence=0.1.
    bets = [make_bet(odds=0.55) for _ in range(10)]
    result = p20_nash_deviation(base_market, bets, {})
    assert result.signal == 0.0
    assert result.confidence == pytest.approx(0.1)


def test_p20_empty_bets(base_market):
    result = p20_nash_deviation(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- P21 ---

def test_p21_high_prob_signals_yes(base_market):
    # Median odds > P21_HIGH_PROB=0.85 → prospect theory: under-bet → signal YES > 0.
    bets = [make_bet(odds=0.90) for _ in range(5)]
    result = p21_prospect_theory(base_market, bets, {})
    assert result.signal > 0.0


def test_p21_low_prob_signals_no(base_market):
    # Median odds < P21_LOW_PROB=0.15 → prospect theory: over-bet → signal NO < 0.
    bets = [make_bet(odds=0.05) for _ in range(5)]
    result = p21_prospect_theory(base_market, bets, {})
    assert result.signal < 0.0


def test_p21_empty_bets(base_market):
    result = p21_prospect_theory(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- P22 ---

def test_p22_too_few_bets(base_market):
    # < P22_MIN_HERD_SIZE=10 → early return.
    result = p22_herding(base_market, [make_bet() for _ in range(9)], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_p22_balanced_bets_no_herding(base_market):
    # 10 bets alternating YES/NO spread evenly → no herding detected.
    bets = [make_bet(side="YES" if i % 2 == 0 else "NO", offset_hours=float(9 - i))
            for i in range(10)]
    result = p22_herding(base_market, bets, {})
    # Balanced bets with low clustering → confidence=0 (not herding)
    assert isinstance(result.signal, float)
    assert result.confidence == 0.0


def test_p22_all_yes_signal_nonzero(base_market):
    # 12 YES bets spread over 12 hours → raw_signal=1.0 (may or may not herd-discount).
    bets = [make_bet(side="YES", amount=100, offset_hours=float(11 - i)) for i in range(12)]
    result = p22_herding(base_market, bets, {})
    assert result.signal > 0.0   # regardless of herding discount, YES dominates


# --- P23 ---

def test_p23_no_anchor_returns_zero(base_market):
    # No bet >= P23_ANCHOR_MIN_AMOUNT=500 → no anchor found → signal=0.
    bets = [make_bet(wallet=f"W{i}", amount=100) for i in range(5)]
    result = p23_anchoring(base_market, bets, {})
    assert result.signal == 0.0
    assert result.metadata.get("reason") == "no anchor found"


def test_p23_strongly_anchored_market(base_market):
    # Anchor bet at odds=0.70, all subsequent bets at odds=0.70 → mean_diff=0 → strength=1.0.
    # Late money (last 25%) all YES → signal = late YES direction > 0.
    anchor = make_bet(wallet="ANCH", side="YES", amount=1000, odds=0.70, offset_hours=5)
    followers = [make_bet(wallet=f"F{i}", side="YES", amount=50, odds=0.70,
                          offset_hours=4.0 - i * 0.3) for i in range(12)]
    result = p23_anchoring(base_market, [anchor] + followers, {})
    assert result.metadata["anchoring_strength"] > 0.7
    assert result.signal > 0.0


def test_p23_empty_bets(base_market):
    result = p23_anchoring(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- P24 ---

def test_p24_madness_regime_boosts_signal(base_market):
    # All wallets have rationality=0.2 < 0.4 → ratio=1.0 > P24_HIGH_RATIO=0.70 → madness.
    # All bets YES → signal=1.0, confidence=1.0.
    bets = [make_bet(wallet=f"W{i}", side="YES", amount=100) for i in range(5)]
    wallets = {f"W{i}": make_wallet(address=f"W{i}", rationality=0.2) for i in range(5)}
    result = p24_wisdom_madness(base_market, bets, wallets)
    assert result.signal == pytest.approx(1.0)
    assert result.metadata["regime"] == "madness"
    assert result.confidence == pytest.approx(1.0)


def test_p24_wisdom_regime_dampens_signal(base_market):
    # All wallets rational (rationality=0.8 > 0.4) → ratio=0 < P24_LOW_RATIO=0.30 → wisdom.
    # Signal dampened to 30%, confidence=0.2.
    bets = [make_bet(wallet=f"W{i}", side="YES", amount=100) for i in range(5)]
    wallets = {f"W{i}": make_wallet(address=f"W{i}", rationality=0.8) for i in range(5)}
    result = p24_wisdom_madness(base_market, bets, wallets)
    assert result.metadata["regime"] == "wisdom"
    assert result.confidence == pytest.approx(0.2)
    assert result.signal == pytest.approx(1.0 * 0.3)


def test_p24_empty_bets(base_market):
    result = p24_wisdom_madness(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0
