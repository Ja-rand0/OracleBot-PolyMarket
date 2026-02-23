"""M25-M28: Markov chain / temporal transition analysis methods."""
from __future__ import annotations

import logging
from collections import defaultdict
from statistics import median

import config
from data.models import Bet, Market, MethodResult, Wallet
from methods import register

log = logging.getLogger(__name__)

# State index constants
_SMALL, _MEDIUM, _LARGE = 0, 1, 2
_LOW, _MID, _HIGH = 0, 1, 2
_YES_HEAVY, _BALANCED, _NO_HEAVY = 0, 1, 2
_SMART_LEADS, _MIXED, _RETAIL_LEADS = 0, 1, 2


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _build_transition_matrix(states: list[int], num_states: int) -> list[list[float]]:
    """Normalized transition probability matrix from a state sequence.

    Returns num_states x num_states matrix where matrix[i][j] = P(j | i).
    Rows with zero transitions get uniform distribution.
    """
    counts = [[0] * num_states for _ in range(num_states)]
    for i in range(len(states) - 1):
        counts[states[i]][states[i + 1]] += 1

    matrix = []
    for row in counts:
        total = sum(row)
        if total == 0:
            matrix.append([1.0 / num_states] * num_states)
        else:
            matrix.append([c / total for c in row])
    return matrix


def _time_windows(bets: list[Bet], num_windows: int) -> list[list[Bet]]:
    """Bucket sorted bets into equal-duration time windows.

    Returns a list of ``num_windows`` lists. Bets must not be empty.
    """
    sorted_bets = sorted(bets, key=lambda b: b.timestamp)
    t_start = sorted_bets[0].timestamp
    t_end = sorted_bets[-1].timestamp
    span = (t_end - t_start).total_seconds()

    if span <= 0:
        return [sorted_bets] + [[] for _ in range(num_windows - 1)]

    windows: list[list[Bet]] = [[] for _ in range(num_windows)]
    for b in sorted_bets:
        idx = int((b.timestamp - t_start).total_seconds() / span * num_windows)
        idx = min(idx, num_windows - 1)
        windows[idx].append(b)
    return windows


def _normalize_odds(bet: Bet) -> float:
    """Return YES probability (odds always stores YES probability post-B001 fix)."""
    return bet.odds


# ---------------------------------------------------------------------------
# M25 -- Wallet Regime Detection
# ---------------------------------------------------------------------------

@register("M25", "M", "Wallet bet-size escalation detection")
def m25_wallet_regime(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    if len(bets) < 5:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "insufficient bets"})

    # Group bets by wallet, sorted by time
    by_wallet: dict[str, list[Bet]] = defaultdict(list)
    for b in bets:
        by_wallet[b.wallet].append(b)

    escalating_wallets: set[str] = set()
    escalation_scores: list[float] = []

    for addr, wbets in by_wallet.items():
        if len(wbets) < config.M25_MIN_WALLET_BETS:
            continue

        wbets.sort(key=lambda b: b.timestamp)
        amounts = [b.amount for b in wbets]
        med = median(amounts)
        if med <= 0:
            continue

        # Classify each bet into size tier
        states: list[int] = []
        for b in wbets:
            if b.amount < med * config.M25_SMALL_MULTIPLIER:
                states.append(_SMALL)
            elif b.amount > med * config.M25_LARGE_MULTIPLIER:
                states.append(_LARGE)
            else:
                states.append(_MEDIUM)

        if len(states) < 2:
            continue

        tm = _build_transition_matrix(states, 3)
        # Escalation = average of upward transition probabilities
        esc = (tm[_SMALL][_MEDIUM] + tm[_MEDIUM][_LARGE] + tm[_SMALL][_LARGE]) / 3.0
        escalation_scores.append(esc)

        if esc >= config.M25_ESCALATION_THRESHOLD:
            escalating_wallets.add(addr)

    if not escalation_scores:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "no wallets with enough bets"})

    if not escalating_wallets:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"wallets_analyzed": len(escalation_scores),
                                      "escalating_wallets": 0,
                                      "avg_escalation_score": sum(escalation_scores) / len(escalation_scores)})

    # Signal from escalating wallets' direction
    yes_vol = sum(b.amount for b in bets if b.wallet in escalating_wallets and b.side == "YES")
    no_vol = sum(b.amount for b in bets if b.wallet in escalating_wallets and b.side == "NO")
    total = yes_vol + no_vol
    signal = (yes_vol - no_vol) / total if total > 0 else 0.0
    confidence = min(1.0, len(escalating_wallets) / config.M25_CONFIDENCE_CAP)

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "wallets_analyzed": len(escalation_scores),
            "escalating_wallets": len(escalating_wallets),
            "avg_escalation_score": sum(escalation_scores) / len(escalation_scores),
            "yes_vol": yes_vol,
            "no_vol": no_vol,
        },
    )


# ---------------------------------------------------------------------------
# M26 -- Market Phase Transitions
# ---------------------------------------------------------------------------

@register("M26", "M", "Market price phase transition detection")
def m26_market_phases(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    if len(bets) < 10:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "insufficient bets"})

    sorted_bets = sorted(bets, key=lambda b: b.timestamp)
    span_seconds = (sorted_bets[-1].timestamp - sorted_bets[0].timestamp).total_seconds()
    if span_seconds < 3600:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "time span < 1 hour"})

    windows = _time_windows(bets, config.M26_NUM_WINDOWS)

    # Classify each window by median YES probability
    window_states: list[int] = []
    window_medians: list[float] = []
    prev_state = _MID

    populated_count = 0
    for w in windows:
        if not w:
            window_states.append(prev_state)
            window_medians.append(-1.0)
            continue
        populated_count += 1
        med = median([_normalize_odds(b) for b in w])
        window_medians.append(med)
        if med < config.M26_LOW_THRESHOLD:
            state = _LOW
        elif med > config.M26_HIGH_THRESHOLD:
            state = _HIGH
        else:
            state = _MID
        window_states.append(state)
        prev_state = state

    if populated_count < 3:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "fewer than 3 populated windows"})

    tm = _build_transition_matrix(window_states, 3)
    trending_score = (tm[_LOW][_LOW] + tm[_MID][_MID] + tm[_HIGH][_HIGH]) / 3.0

    state_labels = {_LOW: "LOW", _MID: "MID", _HIGH: "HIGH"}
    last_state = window_states[-1]

    if trending_score > config.M26_TRENDING_THRESHOLD:
        if last_state == _HIGH:
            signal = 1.0
        elif last_state == _LOW:
            signal = -1.0
        else:
            signal = 0.0
        confidence = min(1.0, (trending_score - 0.33) / 0.34)
    else:
        signal = 0.0
        confidence = 0.1

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "window_states": [state_labels.get(s, "MID") for s in window_states],
            "window_medians": window_medians,
            "trending_score": trending_score,
            "is_trending": trending_score > config.M26_TRENDING_THRESHOLD,
            "last_state": state_labels.get(last_state, "MID"),
        },
    )


# ---------------------------------------------------------------------------
# M27 -- Bet Flow Momentum
# ---------------------------------------------------------------------------

@register("M27", "M", "Bet flow directional momentum detection")
def m27_flow_momentum(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    if len(bets) < 12:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "insufficient bets"})

    sorted_bets = sorted(bets, key=lambda b: b.timestamp)
    span_seconds = (sorted_bets[-1].timestamp - sorted_bets[0].timestamp).total_seconds()
    if span_seconds < 3600:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "time span < 1 hour"})

    windows = _time_windows(bets, config.M27_NUM_WINDOWS)

    # Compute net flow per window
    net_flows: list[float] = []
    for w in windows:
        yes_amt = sum(b.amount for b in w if b.side == "YES")
        no_amt = sum(b.amount for b in w if b.side == "NO")
        net_flows.append(yes_amt - no_amt)

    # Threshold for directional classification
    abs_flows = [abs(nf) for nf in net_flows if nf != 0]
    if len(abs_flows) < 2:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"reason": "no directional flow"})
    med_abs = median(abs_flows)
    threshold = med_abs * config.M27_FLOW_THRESHOLD

    # Classify windows
    window_states: list[int] = []
    populated_count = 0
    for nf in net_flows:
        if nf > threshold:
            window_states.append(_YES_HEAVY)
            populated_count += 1
        elif nf < -threshold:
            window_states.append(_NO_HEAVY)
            populated_count += 1
        else:
            window_states.append(_BALANCED)

    if populated_count < 3:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"reason": "fewer than 3 directional windows"})

    tm = _build_transition_matrix(window_states, 3)
    momentum_score = (tm[_YES_HEAVY][_YES_HEAVY] + tm[_NO_HEAVY][_NO_HEAVY]) / 2.0
    reversal_score = (tm[_YES_HEAVY][_NO_HEAVY] + tm[_NO_HEAVY][_YES_HEAVY]) / 2.0

    flow_labels = {_YES_HEAVY: "YES_HEAVY", _BALANCED: "BALANCED", _NO_HEAVY: "NO_HEAVY"}

    # Find last directional window for signal direction
    last_dir = _BALANCED
    last_dir_idx = -1
    for i in range(len(window_states) - 1, -1, -1):
        if window_states[i] != _BALANCED:
            last_dir = window_states[i]
            last_dir_idx = i
            break

    if momentum_score > config.M27_MOMENTUM_THRESHOLD:
        signal = 1.0 if last_dir == _YES_HEAVY else (-1.0 if last_dir == _NO_HEAVY else 0.0)
        confidence = min(1.0, momentum_score * 1.5)
        regime = "momentum"
    elif reversal_score > momentum_score and reversal_score > 0.3:
        # Contrarian: opposite of last directional window
        signal = -1.0 if last_dir == _YES_HEAVY else (1.0 if last_dir == _NO_HEAVY else 0.0)
        confidence = min(1.0, reversal_score)
        regime = "reversal"
    else:
        signal = 0.0
        confidence = 0.1
        regime = "neutral"

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "window_flows": [flow_labels.get(s, "BALANCED") for s in window_states],
            "window_net_amounts": net_flows,
            "momentum_score": momentum_score,
            "reversal_score": reversal_score,
            "regime": regime,
            "signal_source_window": last_dir_idx,
        },
    )


# ---------------------------------------------------------------------------
# M28 -- Smart-Follow Sequencing
# ---------------------------------------------------------------------------

@register("M28", "M", "Smart-money leader/follower sequencing")
def m28_smart_follow(
    market: Market, bets: list[Bet], wallets: dict[str, Wallet]
) -> MethodResult:
    if len(bets) < 10:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "insufficient bets"})

    # Classify wallets
    smart_addrs: set[str] = set()
    retail_addrs: set[str] = set()
    for addr, w in wallets.items():
        if w.rationality_score >= config.M28_SMART_THRESHOLD:
            smart_addrs.add(addr)
        elif w.rationality_score < config.M28_RETAIL_THRESHOLD:
            retail_addrs.add(addr)

    # Check we have enough of each group in this market's bets
    smart_in_bets = {b.wallet for b in bets} & smart_addrs
    retail_in_bets = {b.wallet for b in bets} & retail_addrs

    if len(smart_in_bets) < config.M28_MIN_SMART_WALLETS:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "insufficient smart wallets",
                                      "smart_wallets": len(smart_in_bets)})
    if len(retail_in_bets) < config.M28_MIN_RETAIL_WALLETS:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "insufficient retail wallets",
                                      "retail_wallets": len(retail_in_bets)})

    sorted_bets = sorted(bets, key=lambda b: b.timestamp)
    span_seconds = (sorted_bets[-1].timestamp - sorted_bets[0].timestamp).total_seconds()
    if span_seconds < 3600:
        return MethodResult(signal=0.0, confidence=0.0, filtered_bets=bets,
                            metadata={"reason": "time span < 1 hour"})

    windows = _time_windows(bets, config.M28_NUM_WINDOWS)

    # Per window: who bets first?
    window_states: list[int] = []
    for w in windows:
        if not w:
            window_states.append(_MIXED)
            continue

        first_smart_ts = None
        first_retail_ts = None
        for b in w:  # already sorted within window by _time_windows
            if first_smart_ts is None and b.wallet in smart_addrs:
                first_smart_ts = b.timestamp
            if first_retail_ts is None and b.wallet in retail_addrs:
                first_retail_ts = b.timestamp
            if first_smart_ts and first_retail_ts:
                break

        if first_smart_ts and first_retail_ts:
            if first_smart_ts < first_retail_ts:
                window_states.append(_SMART_LEADS)
            elif first_retail_ts < first_smart_ts:
                window_states.append(_RETAIL_LEADS)
            else:
                window_states.append(_MIXED)
        elif first_smart_ts:
            window_states.append(_SMART_LEADS)
        elif first_retail_ts:
            window_states.append(_RETAIL_LEADS)
        else:
            window_states.append(_MIXED)

    # Check for meaningful pattern
    non_mixed = [s for s in window_states if s != _MIXED]
    if len(non_mixed) < 2:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"reason": "all windows mixed",
                                      "smart_wallets": len(smart_in_bets),
                                      "retail_wallets": len(retail_in_bets)})

    tm = _build_transition_matrix(window_states, 3)
    smart_lead_persistence = tm[_SMART_LEADS][_SMART_LEADS]

    # Signal: direction of smart money's bets
    smart_yes = sum(b.amount for b in bets if b.wallet in smart_addrs and b.side == "YES")
    smart_no = sum(b.amount for b in bets if b.wallet in smart_addrs and b.side == "NO")
    smart_total = smart_yes + smart_no

    if smart_total <= 0:
        return MethodResult(signal=0.0, confidence=0.1, filtered_bets=bets,
                            metadata={"reason": "no smart money volume"})

    signal = (smart_yes - smart_no) / smart_total

    # Check for contrarian pattern: retail leads, smart follows opposite
    retail_yes = sum(b.amount for b in bets if b.wallet in retail_addrs and b.side == "YES")
    retail_no = sum(b.amount for b in bets if b.wallet in retail_addrs and b.side == "NO")
    retail_total = retail_yes + retail_no
    is_contrarian = False
    if retail_total > 0:
        retail_dir = (retail_yes - retail_no) / retail_total
        # Opposing directions
        if signal * retail_dir < 0:
            is_contrarian = True
            signal = max(-1.0, min(1.0, signal * 1.3))

    confidence = min(1.0, smart_lead_persistence * 2)
    if smart_lead_persistence < 0.3:
        confidence *= 0.3

    leader_labels = {_SMART_LEADS: "SMART_LEADS", _MIXED: "MIXED", _RETAIL_LEADS: "RETAIL_LEADS"}

    return MethodResult(
        signal=signal,
        confidence=confidence,
        filtered_bets=bets,
        metadata={
            "smart_wallets": len(smart_in_bets),
            "retail_wallets": len(retail_in_bets),
            "window_leaders": [leader_labels.get(s, "MIXED") for s in window_states],
            "smart_lead_persistence": smart_lead_persistence,
            "smart_yes_vol": smart_yes,
            "smart_no_vol": smart_no,
            "is_contrarian": is_contrarian,
        },
    )
