import pytest
from methods.statistical import t19_zscore_outlier
from tests.conftest import make_bet, make_wallet


def test_t19_large_rational_bet_signals_yes(base_market):
    # 1 large YES outlier + 9 normal bets → z ≈ 3.0 > T19_ZSCORE_THRESHOLD(2.5).
    # With amounts [5000, 100, 100, ...]: mean≈590, std≈1470, z≈3.0.
    bets = [make_bet(wallet="W1", side="YES", amount=5000)]
    bets += [make_bet(wallet="W2", side="NO", amount=100) for _ in range(9)]
    wallets = {"W1": make_wallet(address="W1", rationality=0.9)}
    result = t19_zscore_outlier(base_market, bets, wallets)
    assert result.signal > 0.0
    assert result.confidence > 0.0

def test_t19_no_outliers_returns_zero(base_market):
    # Tightly clustered amounts [100..104]: max z ≈ 1.4 < 2.5 → no outliers detected
    bets = [make_bet(wallet=f"W{i}", side="YES" if i % 2 == 0 else "NO", amount=100 + i)
            for i in range(5)]
    result = t19_zscore_outlier(base_market, bets, {})
    assert result.signal == 0.0
    assert result.confidence == 0.0

def test_t19_missing_wallet_does_not_crash(base_market):
    # Wallet not in dict → code defaults to rationality=0.5 — must not KeyError.
    # 4 bets triggers early return (< 5) — crash safety is still validated.
    bets = [make_bet(wallet="UNKNOWN", side="YES", amount=5000),
            make_bet(wallet="W2", side="NO", amount=100),
            make_bet(wallet="W2", side="NO", amount=100),
            make_bet(wallet="W2", side="NO", amount=100)]
    result = t19_zscore_outlier(base_market, bets, {})
    assert isinstance(result.signal, float)
    assert 0.0 <= result.confidence <= 1.0

def test_t19_empty_bets(base_market):
    result = t19_zscore_outlier(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0
