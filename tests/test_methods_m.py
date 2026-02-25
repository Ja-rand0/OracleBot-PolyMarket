import pytest
from methods.markov import m26_market_phases, m27_flow_momentum, m28_smart_follow
from tests.conftest import make_bet, make_wallet


def _spread_bets(n, side="YES", odds=0.75, amount=100, hours=5.0):
    """n bets spread evenly from `hours` ago to now."""
    return [make_bet(wallet=f"W{i}", side=side, odds=odds, amount=amount,
                     offset_hours=hours * (n - i - 1) / max(n - 1, 1))
            for i in range(n)]


# --- M26 ---

def test_m26_insufficient_bets(base_market):
    result = m26_market_phases(base_market, [make_bet() for _ in range(9)], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0

def test_m26_short_time_span(base_market):
    # 15 bets all within 30 minutes (< 1 hour minimum).
    bets = [make_bet(offset_hours=0.5 * i / 14) for i in range(15)]
    result = m26_market_phases(base_market, bets, {})
    assert result.signal == 0.0
    assert result.confidence == 0.0

def test_m26_trending_high_signals_yes(base_market):
    # 15 bets at odds=0.75 (> M26_HIGH_THRESHOLD=0.65) spread over 5 hours.
    # All windows → HIGH state → trending_score ≈ 0.56 > M26_TRENDING_THRESHOLD=0.33.
    bets = _spread_bets(15, odds=0.75, hours=5.0)
    result = m26_market_phases(base_market, bets, {})
    assert result.signal == pytest.approx(1.0)
    assert result.confidence > 0.0

def test_m26_trending_low_signals_no(base_market):
    # 15 bets at odds=0.20 (< M26_LOW_THRESHOLD=0.35) → all LOW → signal=-1.0.
    bets = _spread_bets(15, odds=0.20, hours=5.0)
    result = m26_market_phases(base_market, bets, {})
    assert result.signal == pytest.approx(-1.0)


# --- M27 ---

def test_m27_insufficient_bets(base_market):
    result = m27_flow_momentum(base_market, [make_bet() for _ in range(11)], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0

def test_m27_short_time_span(base_market):
    bets = [make_bet(offset_hours=0.5 * i / 14) for i in range(15)]
    result = m27_flow_momentum(base_market, bets, {})
    assert result.signal == 0.0
    assert result.confidence == 0.0

def test_m27_momentum_yes_signals_yes(base_market):
    # 15 YES bets spread over 5 hours → all windows YES_HEAVY →
    # momentum_score = (1.0 + 1/3) / 2 ≈ 0.67 > M27_MOMENTUM_THRESHOLD=0.60 → signal=1.0.
    bets = _spread_bets(15, side="YES", hours=5.0)
    result = m27_flow_momentum(base_market, bets, {})
    assert result.signal == pytest.approx(1.0)
    assert result.metadata["regime"] == "momentum"


# --- M28 ---

def test_m28_insufficient_bets(base_market):
    result = m28_smart_follow(base_market, [make_bet() for _ in range(9)], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0

def test_m28_insufficient_smart_wallets(base_market):
    # Only 1 smart wallet → < M28_MIN_SMART_WALLETS=3 → early return.
    bets = [make_bet(wallet="S1", side="YES", amount=100)] * 10
    wallets = {"S1": make_wallet(address="S1", rationality=0.7)}
    result = m28_smart_follow(base_market, bets, wallets)
    assert result.signal == 0.0
    assert "insufficient" in result.metadata.get("reason", "")

def test_m28_smart_leads_yes_signals_yes(base_market):
    # 3 smart wallets (rationality=0.7), 3 retail wallets (rationality=0.3).
    # Per window: smart bets first (higher offset = older), retail slightly after.
    # All smart bets are YES → signal > 0, confidence > 0.
    smart_addrs = [f"S{i}" for i in range(3)]
    retail_addrs = [f"R{i}" for i in range(3)]

    bets = []
    for window in range(5):
        h_base = float(4 - window)   # windows from 4h ago to 0h
        for j, addr in enumerate(smart_addrs):
            bets.append(make_bet(wallet=addr, side="YES", amount=100,
                                 offset_hours=h_base + 0.1))
        for j, addr in enumerate(retail_addrs):
            bets.append(make_bet(wallet=addr, side="NO", amount=100,
                                 offset_hours=h_base + 0.05))

    wallets = ({addr: make_wallet(address=addr, rationality=0.7) for addr in smart_addrs} |
               {addr: make_wallet(address=addr, rationality=0.3) for addr in retail_addrs})

    result = m28_smart_follow(base_market, bets, wallets)
    assert result.signal > 0.0
    assert result.confidence > 0.0
