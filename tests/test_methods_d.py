import pytest
from methods.discrete import d5_vacuous_truth, d7_pigeonhole, d8_boolean_sat
from tests.conftest import make_bet, make_wallet


# --- D5 ---

def test_d5_near_certain_yes(base_market):
    bets = [make_bet(odds=0.96), make_bet(odds=0.97), make_bet(odds=0.98)]
    result = d5_vacuous_truth(base_market, bets, {})
    assert result.signal == 1.0
    assert result.confidence > 0.0


def test_d5_near_certain_no(base_market):
    bets = [make_bet(odds=0.02), make_bet(odds=0.03), make_bet(odds=0.04)]
    result = d5_vacuous_truth(base_market, bets, {})
    assert result.signal == -1.0
    assert result.confidence > 0.0


def test_d5_neutral_market(base_market):
    bets = [make_bet(odds=0.48), make_bet(odds=0.50), make_bet(odds=0.52)]
    result = d5_vacuous_truth(base_market, bets, {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_d5_empty_bets(base_market):
    result = d5_vacuous_truth(base_market, [], {})
    assert result.signal == 0.0


# --- D7 ---

def test_d7_few_sharp_wallets_full_confidence(base_market):
    # 9 wallets, sqrt(9)=3, only 2 sharp (win_rate > 0.65) → sharp_count <= max_insiders → confidence=1.0
    bets = [make_bet(wallet=f"W{i}", side="YES", amount=100) for i in range(9)]
    wallets = {f"W{i}": make_wallet(address=f"W{i}", total_bets=10,
               win_rate=0.70 if i < 2 else 0.40) for i in range(9)}
    result = d7_pigeonhole(base_market, bets, wallets)
    assert result.confidence == pytest.approx(1.0)


def test_d7_many_sharp_wallets_discounts_confidence(base_market):
    # 9 wallets, sqrt(9)=3, all 9 sharp → noise_ratio = 1-(3/9) = 0.667 → confidence < 1.0
    bets = [make_bet(wallet=f"W{i}", side="YES", amount=100) for i in range(9)]
    wallets = {f"W{i}": make_wallet(address=f"W{i}", total_bets=10, win_rate=0.80)
               for i in range(9)}
    result = d7_pigeonhole(base_market, bets, wallets)
    assert result.confidence < 1.0


def test_d7_wallets_below_min_bets_not_counted(base_market):
    # W1 has total_bets=2 < D7_MIN_BETS(5) → excluded from qualified → sharp_count=0 → no discount
    bets = [make_bet(wallet="W1", side="YES")]
    wallets = {"W1": make_wallet(address="W1", total_bets=2, win_rate=0.90)}
    result = d7_pigeonhole(base_market, bets, wallets)
    assert result.confidence == pytest.approx(1.0)


# --- D8 ---

@pytest.mark.parametrize("yes_count, no_count, expected_signal", [
    (8, 2, 1.0),
    (2, 8, -1.0),
    (5, 5, 0.0),
])
def test_d8_signal(base_market, yes_count, no_count, expected_signal):
    bets = ([make_bet(side="YES") for _ in range(yes_count)] +
            [make_bet(side="NO") for _ in range(no_count)])
    result = d8_boolean_sat(base_market, bets, {})
    assert result.signal == pytest.approx(expected_signal, abs=0.01)


def test_d8_empty_bets(base_market):
    result = d8_boolean_sat(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0


# --- D9 ---

from methods.discrete import d9_set_partition


def test_d9_emotional_wallets_filtered(base_market):
    # W1: rationality=0.2 < 0.4 → emotional → filtered out
    # W2: rationality=0.6 >= 0.4 → clean → YES signal
    bets = ([make_bet(wallet="W1", side="NO", amount=100) for _ in range(3)] +
            [make_bet(wallet="W2", side="YES", amount=100) for _ in range(3)])
    wallets = {"W1": make_wallet(address="W1", rationality=0.2),
               "W2": make_wallet(address="W2", rationality=0.6)}
    result = d9_set_partition(base_market, bets, wallets)
    assert result.signal == pytest.approx(1.0)
    assert all(b.wallet == "W2" for b in result.filtered_bets)


def test_d9_all_clean_bets_unchanged(base_market):
    # No wallet with rationality < 0.4 → all bets pass through
    bets = [make_bet(wallet=f"W{i}", side="YES") for i in range(4)]
    wallets = {f"W{i}": make_wallet(address=f"W{i}", rationality=0.7) for i in range(4)}
    result = d9_set_partition(base_market, bets, wallets)
    assert len(result.filtered_bets) == 4


def test_d9_empty_bets(base_market):
    result = d9_set_partition(base_market, [], {})
    assert result.signal == 0.0
    assert result.confidence == 0.0
