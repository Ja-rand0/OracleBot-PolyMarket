from datetime import datetime, timedelta
import pytest
from data.models import Market, Bet, Wallet


@pytest.fixture
def base_market():
    now = datetime.utcnow()
    return Market(
        id="test-market-1",
        title="Test Market",
        description="",
        end_date=now + timedelta(days=7),
        resolved=False,
        created_at=now - timedelta(days=7),
    )


def make_bet(market_id="test-market-1", wallet="W1", side="YES",
             amount=100.0, odds=0.6, offset_hours=0):
    return Bet(
        market_id=market_id,
        wallet=wallet,
        side=side,
        amount=amount,
        odds=odds,
        timestamp=datetime.utcnow() - timedelta(hours=offset_hours),
    )


def make_wallet(address="W1", total_bets=10, win_rate=0.5, rationality=0.5):
    return Wallet(
        address=address,
        first_seen=datetime.utcnow() - timedelta(days=30),
        total_bets=total_bets,
        total_volume=1000.0,
        win_rate=win_rate,
        rationality_score=rationality,
    )
