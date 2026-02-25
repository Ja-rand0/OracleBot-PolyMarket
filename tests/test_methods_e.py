import pytest
from methods.emotional import e10_loyalty_bias, e15_round_number, e16_bipartite_pruning
from tests.conftest import make_bet, make_wallet


# --- E10 ---

def test_e10_loyal_yes_wallet_filtered(base_market):
    # W1: 9 YES / 1 NO = 90% YES >= E10_CONSISTENCY_THRESHOLD(0.85) → flagged.
    # W2: 2 bets (< E10_MIN_MARKETS=3) → not checked → passes through at 50/50.
    bets = [make_bet(wallet="W1", side="YES") for _ in range(9)]
    bets += [make_bet(wallet="W1", side="NO")]
    bets += [make_bet(wallet="W2", side="YES", amount=200)]
    bets += [make_bet(wallet="W2", side="NO", amount=200)]
    result = e10_loyalty_bias(base_market, bets, {})
    assert -0.15 <= result.signal <= 0.15   # W2 is 50/50 → near 0
    assert result.confidence > 0.0

def test_e10_no_loyalty_returns_all_bets(base_market):
    # Each wallet has 2 bets < E10_MIN_MARKETS(3) → none flagged
    bets = [make_bet(wallet="W1", side="YES"), make_bet(wallet="W1", side="NO"),
            make_bet(wallet="W2", side="YES"), make_bet(wallet="W2", side="NO")]
    result = e10_loyalty_bias(base_market, bets, {})
    assert len(result.filtered_bets) == len(bets)

def test_e10_empty_bets(base_market):
    result = e10_loyalty_bias(base_market, [], {})
    assert result.signal == 0.0
    # Code returns 0.1 (not 0.0) for empty bets — the else branch of confidence formula
    assert result.confidence == pytest.approx(0.1)


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
    # W1: 10 YES / 0 NO → KL(p||uniform) ≈ 0.693 >> E16_KL_THRESHOLD(0.5) → flagged.
    # 9 YES/1 NO only gives KL ≈ 0.368 which is below threshold.
    # W2: 1 bet only (<3) → not checked → passes through. Clean bets are all NO.
    bets = [make_bet(wallet="W1", side="YES") for _ in range(10)]
    bets += [make_bet(wallet="W2", side="NO", amount=200)]
    result = e16_bipartite_pruning(base_market, bets, {})
    assert result.signal < 0.0

def test_e16_balanced_wallet_not_flagged(base_market):
    bets = [make_bet(wallet="W1", side="YES") for _ in range(5)]
    bets += [make_bet(wallet="W1", side="NO") for _ in range(5)]
    result = e16_bipartite_pruning(base_market, bets, {})
    assert len(result.filtered_bets) == 10   # W1 not flagged → all returned

def test_e16_empty_bets(base_market):
    result = e16_bipartite_pruning(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0
