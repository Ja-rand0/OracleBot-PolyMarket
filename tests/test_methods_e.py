import pytest
from methods.emotional import (
    e10_loyalty_bias, e11_recency_bias, e12_revenge_betting,
    e13_hype_detection, e14_odds_sensitivity,
    e15_round_number, e16_bipartite_pruning,
)
from tests.conftest import make_bet, make_wallet


# --- E10 ---

def test_e10_loyal_yes_wallet_filtered(base_market):
    # W1: yes_bet_ratio=0.9 across all markets (>= E10_CONSISTENCY_THRESHOLD=0.85) → flagged.
    # W2: yes_bet_ratio=0.5 (balanced) and only 2 total bets → not checked.
    bets = [make_bet(wallet="W1", side="YES") for _ in range(9)]
    bets += [make_bet(wallet="W1", side="NO")]
    bets += [make_bet(wallet="W2", side="YES", amount=200)]
    bets += [make_bet(wallet="W2", side="NO", amount=200)]
    wallets = {"W1": make_wallet(address="W1", yes_bet_ratio=0.9, total_bets=10),
               "W2": make_wallet(address="W2", yes_bet_ratio=0.5, total_bets=2)}
    result = e10_loyalty_bias(base_market, bets, wallets)
    assert -0.15 <= result.signal <= 0.15   # W2 is 50/50 → near 0
    assert result.confidence > 0.0

def test_e10_no_loyalty_returns_all_bets(base_market):
    # All wallets have yes_bet_ratio=0.5 (balanced cross-market) → none flagged.
    bets = [make_bet(wallet="W1", side="YES"), make_bet(wallet="W1", side="NO"),
            make_bet(wallet="W2", side="YES"), make_bet(wallet="W2", side="NO")]
    wallets = {f"W{i}": make_wallet(address=f"W{i}", yes_bet_ratio=0.5) for i in range(1, 3)}
    result = e10_loyalty_bias(base_market, bets, wallets)
    assert len(result.filtered_bets) == len(bets)

def test_e10_empty_bets(base_market):
    result = e10_loyalty_bias(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- E15 ---

def test_e15_round_wallet_flagged_clean_signal_negative(base_market):
    # W1: all round (100, 200, 50 all divisible by E15_ROUND_DIVISOR=50) → flagged.
    # W2: precise amounts (47 < 50, 113 % 50 != 0) → clean, all NO → signal < 0.
    bets = [make_bet(wallet="W1", side="YES", amount=100),
            make_bet(wallet="W1", side="YES", amount=200),
            make_bet(wallet="W1", side="YES", amount=50),
            make_bet(wallet="W2", side="NO", amount=47),
            make_bet(wallet="W2", side="NO", amount=113)]
    result = e15_round_number(base_market, bets, {})
    assert result.signal < 0.0   # clean bets are all NO

def test_e15_precise_bets_not_flagged(base_market):
    bets = [make_bet(wallet="W1", side="YES", amount=47),
            make_bet(wallet="W1", side="YES", amount=113),
            make_bet(wallet="W1", side="YES", amount=251)]
    result = e15_round_number(base_market, bets, {})
    assert len(result.filtered_bets) == 3

def test_e15_empty_bets(base_market):
    result = e15_round_number(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- E16 ---

def test_e16_skewed_wallet_flagged(base_market):
    # W1: yes_bet_ratio=0.99 cross-market → KL ≈ 0.693 >> E16_KL_THRESHOLD(0.5) → flagged.
    # W2: no wallet entry (<3 total_bets default) → not checked → passes through (all NO).
    bets = [make_bet(wallet="W1", side="YES") for _ in range(10)]
    bets += [make_bet(wallet="W2", side="NO", amount=200)]
    wallets = {"W1": make_wallet(address="W1", yes_bet_ratio=0.99, total_bets=20)}
    result = e16_bipartite_pruning(base_market, bets, wallets)
    assert result.signal < 0.0

def test_e16_balanced_wallet_not_flagged(base_market):
    bets = [make_bet(wallet="W1", side="YES") for _ in range(5)]
    bets += [make_bet(wallet="W1", side="NO") for _ in range(5)]
    wallets = {"W1": make_wallet(address="W1", yes_bet_ratio=0.5, total_bets=20)}
    result = e16_bipartite_pruning(base_market, bets, wallets)
    assert len(result.filtered_bets) == 10   # W1 not flagged → all returned

def test_e16_empty_bets(base_market):
    result = e16_bipartite_pruning(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- E11 ---

def test_e11_recency_bias_filters_early_wallet(base_market):
    # 5 bets: oldest = EARLY wallet (YES); last 4 = LATE wallet (NO).
    # First 20% = 1 bet → early_ratio=1.0, late_ratio=0.0, skew=1.0 > 0.3.
    # EARLY wallet only bets early → filtered; clean bets are all NO → signal=-1.0.
    bets = ([make_bet(wallet="EARLY", side="YES", offset_hours=4)] +
            [make_bet(wallet="LATE", side="NO", offset_hours=3 - i) for i in range(4)])
    result = e11_recency_bias(base_market, bets, {})
    assert result.signal == pytest.approx(-1.0)
    assert result.confidence > 0.3

def test_e11_no_bias_when_consistent(base_market):
    # 10 bets: same YES ratio early and late → skew ≤ 0.3 → no filtering.
    bets = [make_bet(wallet=f"W{i}", side="YES" if i % 2 == 0 else "NO",
                     offset_hours=float(9 - i)) for i in range(10)]
    result = e11_recency_bias(base_market, bets, {})
    assert len(result.filtered_bets) == 10

def test_e11_too_few_bets(base_market):
    result = e11_recency_bias(base_market, [make_bet() for _ in range(4)], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- E12 ---

def test_e12_revenge_bettor_filtered(base_market):
    # W1: bet 100 then 200 (>= 1.5x, >100) within E12_WINDOW_HOURS=24 → revenge → filtered.
    # W2: clean NO bets → signal = -1.0.
    bets = ([make_bet(wallet="W1", side="YES", amount=100, offset_hours=2),
             make_bet(wallet="W1", side="YES", amount=200, offset_hours=1)] +
            [make_bet(wallet="W2", side="NO", amount=100) for _ in range(3)])
    result = e12_revenge_betting(base_market, bets, {})
    assert result.signal == pytest.approx(-1.0)
    assert result.metadata["revenge_wallets"] == 1

def test_e12_normal_wallet_not_filtered(base_market):
    # W1: amounts 100 → 90 (not 1.5x) → not revenge.
    bets = [make_bet(wallet="W1", side="YES", amount=100, offset_hours=2),
            make_bet(wallet="W1", side="YES", amount=90, offset_hours=1),
            make_bet(wallet="W2", side="NO", amount=100)]
    result = e12_revenge_betting(base_market, bets, {})
    assert result.metadata["revenge_wallets"] == 0
    assert len(result.filtered_bets) == 3

def test_e12_empty_bets(base_market):
    result = e12_revenge_betting(base_market, [], {})
    assert result.signal == 0.0


# --- E13 ---

def test_e13_spike_hour_filtered(base_market):
    # 5 bets (YES) in hour 0 at high volume + 6 bets (NO) spread over hours 1-3.
    # Spike threshold = median * 3.0 → hour 0 spike bets removed → signal < 0.
    spike = [make_bet(wallet=f"S{i}", side="YES", amount=1000,
                      offset_hours=5.0 - i * 0.1) for i in range(5)]
    base  = [make_bet(wallet=f"B{i}", side="NO", amount=100,
                      offset_hours=3.9 - i * 0.9) for i in range(6)]
    result = e13_hype_detection(base_market, spike + base, {})
    assert result.signal <= 0.0   # spike (YES) removed; remaining are NO
    assert result.metadata["spike_bets"] > 0

def test_e13_no_spike_uniform(base_market):
    # 12 bets uniformly spread: 3 per hour over 4 hours, same amount → no spike.
    bets = [make_bet(wallet=f"W{i}", side="YES", amount=100,
                     offset_hours=3.0 - i * 0.25) for i in range(12)]
    result = e13_hype_detection(base_market, bets, {})
    assert result.metadata["spike_bets"] == 0

def test_e13_too_few_bets(base_market):
    result = e13_hype_detection(base_market, [make_bet() for _ in range(9)], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- E14 ---

def test_e14_flat_betting_flagged(base_market):
    # W1: 3 bets all same amount=100 → std(amounts)=0 → emotional → filtered.
    # W2: varying amounts [50,100,200] at varying odds → |corr|>0.3 → not filtered → signal < 0.
    bets = ([make_bet(wallet="W1", side="YES", amount=100, odds=0.3 + i * 0.2)
             for i in range(3)] +
            [make_bet(wallet="W2", side="NO", amount=50 * (i + 1), odds=0.3 + i * 0.2)
             for i in range(3)])
    result = e14_odds_sensitivity(base_market, bets, {})
    assert result.signal < 0.0
    assert result.metadata["emotional_wallets"] == 1

def test_e14_odds_sensitive_not_flagged(base_market):
    # W1: amounts [50, 100, 200] at odds [0.3, 0.5, 0.7] → clear correlation → not flagged.
    bets = [make_bet(wallet="W1", side="YES", amount=50, odds=0.3),
            make_bet(wallet="W1", side="YES", amount=100, odds=0.5),
            make_bet(wallet="W1", side="YES", amount=200, odds=0.7)]
    result = e14_odds_sensitivity(base_market, bets, {})
    assert result.metadata["emotional_wallets"] == 0
    assert len(result.filtered_bets) == 3

def test_e14_single_bet_wallets_skipped(base_market):
    # Wallets with < 3 bets are not checked → all pass through.
    bets = [make_bet(wallet="W1", side="YES", amount=100),
            make_bet(wallet="W2", side="NO", amount=100)]
    result = e14_odds_sensitivity(base_market, bets, {})
    assert len(result.filtered_bets) == 2
