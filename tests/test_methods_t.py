import pytest
from methods.statistical import t17_bayesian, t18_benfords_law, t19_zscore_outlier
from tests.conftest import make_bet, make_wallet


# --- T17 ---

def test_t17_smart_leans_yes_public_no(base_market):
    # Smart wallets (rationality=0.7 >= T17_RATIONALITY_CUTOFF=0.58) bet YES at 500.
    # Emotional wallets (rationality=0.3 < 0.58) bet NO at 100.
    # Smart posterior > public posterior → divergence > 0 → signal > 0.
    bets = ([make_bet(wallet=f"S{i}", side="YES", amount=500, odds=0.5)
             for i in range(2)] +
            [make_bet(wallet=f"E{i}", side="NO", amount=100, odds=0.5)
             for i in range(8)])
    wallets = ({f"S{i}": make_wallet(address=f"S{i}", rationality=0.7) for i in range(2)} |
               {f"E{i}": make_wallet(address=f"E{i}", rationality=0.3) for i in range(8)})
    result = t17_bayesian(base_market, bets, wallets)
    assert result.signal > 0.0

def test_t17_no_smart_wallets_balanced_bets(base_market):
    # All wallets below T17_RATIONALITY_CUTOFF=0.58 (smart_count=0 → smart_posterior=prior).
    # Equal YES and NO bets → public_posterior ≈ prior → divergence ≈ 0 → low signal.
    bets = ([make_bet(wallet=f"W{i}", side="YES", amount=100, odds=0.5) for i in range(5)] +
            [make_bet(wallet=f"W{i}", side="NO", amount=100, odds=0.5) for i in range(5, 10)])
    wallets = {f"W{i}": make_wallet(address=f"W{i}", rationality=0.3) for i in range(10)}
    result = t17_bayesian(base_market, bets, wallets)
    assert result.metadata["smart_bets"] == 0
    assert abs(result.signal) < 0.2   # balanced public → near-zero divergence

def test_t17_empty_bets(base_market):
    result = t17_bayesian(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- T18 ---

def test_t18_all_same_amount_flagged(base_market):
    # 20 bets all at amount=100 → all leading digits = 1 → chi2 >> threshold → suspicious.
    bets = [make_bet(wallet=f"W{i}", side="YES", amount=100) for i in range(20)]
    result = t18_benfords_law(base_market, bets, {})
    assert result.metadata["is_suspicious"]
    assert result.confidence > 0.5

def test_t18_too_few_bets(base_market):
    bets = [make_bet(wallet=f"W{i}", amount=100) for i in range(19)]
    result = t18_benfords_law(base_market, bets, {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


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
