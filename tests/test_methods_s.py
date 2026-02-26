import pytest
from methods.suspicious import s1_win_rate_outlier, s4_sandpit_filter
from tests.conftest import make_bet, make_wallet


# --- S1 ---

def test_s1_sharp_wallet_signals_yes(base_market):
    # 10 wallets: 9 at win_rate=0.50, 1 sharp at 0.70.
    # mean=0.52, std≈0.06, threshold≈0.64 → W9 (0.70) is sharp and bets YES → signal > 0.
    bets = [make_bet(wallet=f"W{i}", side="YES" if i == 9 else "NO", amount=100)
            for i in range(10)]
    wallets = {f"W{i}": make_wallet(address=f"W{i}", total_bets=15,
               win_rate=0.70 if i == 9 else 0.50) for i in range(10)}
    result = s1_win_rate_outlier(base_market, bets, wallets)
    assert result.signal > 0.0


def test_s1_insufficient_qualified_wallets(base_market):
    # Only 2 wallets with total_bets >= S1_MIN_RESOLVED_BETS=10 → < 3 qualified → signal=0.
    bets = [make_bet(wallet="W1"), make_bet(wallet="W2")]
    wallets = {"W1": make_wallet(address="W1", total_bets=15, win_rate=0.80),
               "W2": make_wallet(address="W2", total_bets=15, win_rate=0.40)}
    result = s1_win_rate_outlier(base_market, bets, wallets)
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_s1_zero_stddev_returns_empty(base_market):
    # All 5 wallets have identical win_rate → std=0 → early return.
    bets = [make_bet(wallet=f"W{i}") for i in range(5)]
    wallets = {f"W{i}": make_wallet(address=f"W{i}", total_bets=15, win_rate=0.60)
               for i in range(5)}
    result = s1_win_rate_outlier(base_market, bets, wallets)
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- S4 ---

def test_s4_flagged_wallet_removed(base_market):
    # Wallet with flagged_sandpit=True is stripped; remaining YES balance unchanged.
    bets = [make_bet(wallet="BAD", side="YES", amount=100),
            make_bet(wallet="GOOD", side="NO", amount=100)]
    bad = make_wallet(address="BAD")
    bad.flagged_sandpit = True
    wallets = {"BAD": bad, "GOOD": make_wallet(address="GOOD")}
    result = s4_sandpit_filter(base_market, bets, wallets)
    assert all(b.wallet != "BAD" for b in result.filtered_bets)
    assert result.confidence == pytest.approx(0.5)


def test_s4_volume_based_sandpit_removed(base_market):
    # S4_SANDPIT_MIN_BETS=10, S4_SANDPIT_MAX_WIN_RATE=0.25, S4_SANDPIT_MIN_VOLUME=5000.
    bets = [make_bet(wallet="SAND", side="YES", amount=100)]
    w = make_wallet(address="SAND", total_bets=20, win_rate=0.10)
    w.total_volume = 6000.0
    result = s4_sandpit_filter(base_market, bets, {"SAND": w})
    assert len(result.filtered_bets) == 0


def test_s4_new_wallet_large_bet_removed(base_market):
    # S4_NEW_WALLET_MAX_BETS=3, S4_NEW_WALLET_LARGE_BET=2000.
    bets = [make_bet(wallet="NEW", side="YES", amount=3000)]
    w = make_wallet(address="NEW", total_bets=2, win_rate=0.5)
    result = s4_sandpit_filter(base_market, bets, {"NEW": w})
    assert len(result.filtered_bets) == 0


def test_s4_clean_wallets_unchanged(base_market):
    # No sandpit criteria met → all bets returned, low confidence.
    bets = [make_bet(wallet="W1", side="YES"), make_bet(wallet="W2", side="NO")]
    wallets = {"W1": make_wallet(address="W1", total_bets=50, win_rate=0.5),
               "W2": make_wallet(address="W2", total_bets=50, win_rate=0.5)}
    result = s4_sandpit_filter(base_market, bets, wallets)
    assert len(result.filtered_bets) == 2
    assert result.confidence == pytest.approx(0.1)
