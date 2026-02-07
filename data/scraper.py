from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

import config
from data.models import Bet, Market

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session with retry / backoff
# ---------------------------------------------------------------------------

_session = requests.Session()
_session.headers.update({"Accept": "application/json"})


def _get(url: str, params: dict | None = None) -> Any:
    """GET with retries + exponential backoff."""
    for attempt in range(1, config.API_MAX_RETRIES + 1):
        try:
            resp = _session.get(url, params=params, timeout=config.API_REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            wait = config.API_RETRY_BACKOFF ** attempt
            log.warning("API request failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt, config.API_MAX_RETRIES, exc, wait)
            if attempt == config.API_MAX_RETRIES:
                log.error("API request failed after %d attempts: %s", config.API_MAX_RETRIES, url)
                raise
            time.sleep(wait)


# ---------------------------------------------------------------------------
# Gamma API — Market discovery (richest metadata)
# ---------------------------------------------------------------------------

def _parse_gamma_market(raw: dict) -> Market:
    end_date_str = raw.get("endDate") or raw.get("end_date_iso") or ""
    created_str = raw.get("createdAt") or raw.get("startDate") or ""

    def _parse_dt(s: str) -> datetime:
        if not s:
            return datetime.now(timezone.utc)
        # Handle both "2025-10-29T19:00:43Z" and "2025-10-29T19:01:04.738799Z"
        s = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s).replace(tzinfo=None)
        except ValueError:
            return datetime.now(timezone.utc).replace(tzinfo=None)

    # Determine if resolved and outcome
    closed = raw.get("closed", False)
    resolved = False
    outcome = None
    tokens = raw.get("tokens", [])
    if closed and tokens:
        for tok in tokens:
            if tok.get("winner"):
                resolved = True
                outcome = tok.get("outcome", "").upper()  # "YES" or "NO"
                break

    return Market(
        id=raw.get("conditionId") or raw.get("condition_id", ""),
        title=raw.get("question", ""),
        description=raw.get("description", ""),
        end_date=_parse_dt(end_date_str),
        resolved=resolved,
        outcome=outcome,
        created_at=_parse_dt(created_str),
    )


def fetch_markets(active_only: bool = True, limit: int = 100, max_pages: int = 50) -> list[Market]:
    """Fetch markets from the Gamma API with offset pagination."""
    markets: list[Market] = []
    offset = 0

    for page in range(max_pages):
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if active_only:
            params["active"] = "true"
            params["closed"] = "false"

        log.info("Fetching markets page %d (offset=%d)", page + 1, offset)
        data = _get(config.GAMMA_MARKETS_ENDPOINT, params=params)

        if not data:
            break

        for raw in data:
            try:
                markets.append(_parse_gamma_market(raw))
            except Exception:
                log.exception("Failed to parse market: %s", raw.get("conditionId", "?"))

        if len(data) < limit:
            break  # last page
        offset += limit

    log.info("Fetched %d markets total", len(markets))
    return markets


def _parse_clob_market(raw: dict) -> Market:
    """Parse a market from the CLOB API (has winner info on tokens)."""
    end_str = raw.get("end_date_iso", "")
    created_str = raw.get("accepting_order_timestamp", "")

    def _parse_dt(s: str) -> datetime:
        if not s:
            return datetime.now(timezone.utc).replace(tzinfo=None)
        s = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s).replace(tzinfo=None)
        except ValueError:
            return datetime.now(timezone.utc).replace(tzinfo=None)

    tokens = raw.get("tokens", [])
    resolved = False
    outcome = None
    for i, tok in enumerate(tokens):
        if tok.get("winner"):
            resolved = True
            # Normalize: map to YES/NO based on token index
            # tokens[0] = YES side, tokens[1] = NO side
            out = tok.get("outcome", "")
            if out.lower() in ("yes", "no"):
                outcome = out.upper()
            else:
                outcome = "YES" if i == 0 else "NO"
            break

    return Market(
        id=raw.get("condition_id", ""),
        title=raw.get("question", ""),
        description=raw.get("description", ""),
        end_date=_parse_dt(end_str),
        resolved=resolved,
        outcome=outcome,
        created_at=_parse_dt(created_str),
    )


def fetch_resolved_markets(limit: int = 1000, max_pages: int = 10) -> list[Market]:
    """Fetch resolved/closed markets from the CLOB API (has winner data)."""
    markets: list[Market] = []
    cursor = "MA=="  # base64 for "0"

    for page in range(max_pages):
        log.info("Fetching resolved markets page %d (cursor=%s)", page + 1, cursor[:8])
        data = _get(config.POLYMARKET_MARKETS_ENDPOINT, params={"next_cursor": cursor})

        if not data or "data" not in data:
            break

        for raw in data["data"]:
            try:
                if raw.get("closed"):
                    m = _parse_clob_market(raw)
                    if m.resolved and m.outcome:
                        markets.append(m)
            except Exception:
                log.exception("Failed to parse CLOB market: %s",
                              raw.get("condition_id", "?"))

        cursor = data.get("next_cursor", "LTE=")
        if cursor == "LTE=":  # base64 for "-1" = end
            break

    log.info("Fetched %d resolved markets total", len(markets))
    return markets


# ---------------------------------------------------------------------------
# Data API — Public trade history (no auth needed)
# ---------------------------------------------------------------------------

def _parse_trade(raw: dict, condition_id: str) -> Bet:
    ts = raw.get("timestamp", 0)
    if isinstance(ts, (int, float)):
        dt = datetime.utcfromtimestamp(ts)
    else:
        dt = datetime.utcnow()

    side_raw = raw.get("side", "BUY")
    outcome = raw.get("outcome", "")
    outcome_index = raw.get("outcomeIndex", 0)

    # Determine bet side using outcomeIndex (0=YES token, 1=NO token)
    if outcome.lower() in ("yes", "no"):
        # Simple YES/NO market
        if side_raw == "BUY":
            side = outcome.upper()
        else:
            side = "NO" if outcome.upper() == "YES" else "YES"
    else:
        # Multi-outcome market: use outcomeIndex
        # BUY on index 0 = YES, BUY on index 1 = NO
        if side_raw == "BUY":
            side = "YES" if outcome_index == 0 else "NO"
        else:
            side = "NO" if outcome_index == 0 else "YES"

    return Bet(
        market_id=condition_id,
        wallet=raw.get("proxyWallet", ""),
        side=side,
        amount=float(raw.get("size", 0)),
        odds=float(raw.get("price", 0)),
        timestamp=dt,
    )


def fetch_trades_for_market(
    condition_id: str,
    limit: int = 500,
    max_pages: int = 20,
    since: datetime | None = None,
) -> list[Bet]:
    """Fetch public trades for a market from the Data API."""
    data_api_url = "https://data-api.polymarket.com/trades"
    bets: list[Bet] = []
    offset = 0

    for page in range(max_pages):
        params: dict[str, Any] = {
            "market": condition_id,
            "limit": min(limit, 10000),
            "offset": offset,
        }

        log.debug("Fetching trades for %s page %d (offset=%d)", condition_id[:16], page + 1, offset)
        try:
            data = _get(data_api_url, params=params)
        except requests.RequestException:
            log.warning("Trade fetch stopped for %s at offset %d (API limit)",
                        condition_id[:16], offset)
            break

        if not data:
            break

        for raw in data:
            try:
                bet = _parse_trade(raw, condition_id)
                if since and bet.timestamp <= since:
                    continue
                bets.append(bet)
            except Exception:
                log.exception("Failed to parse trade in market %s", condition_id[:16])

        if len(data) < limit:
            break
        offset += limit

    log.info("Fetched %d trades for market %s", len(bets), condition_id[:16])
    return bets


# ---------------------------------------------------------------------------
# CLOB API — Order book snapshots
# ---------------------------------------------------------------------------

def fetch_orderbook(token_id: str) -> dict:
    """Fetch order book for a token from the CLOB API."""
    url = f"{config.POLYMARKET_BASE_URL}/book"
    data = _get(url, params={"token_id": token_id})
    return data


def fetch_price_history(condition_id: str, interval: str = "1d", fidelity: int = 60) -> list[dict]:
    """Fetch price history for a market. interval: 1h, 6h, 1d, 1w, max."""
    url = f"{config.POLYMARKET_BASE_URL}/prices-history"
    data = _get(url, params={"market": condition_id, "interval": interval, "fidelity": fidelity})
    return data.get("history", []) if data else []


# ---------------------------------------------------------------------------
# Polygon on-chain (optional, requires API key)
# ---------------------------------------------------------------------------

def fetch_wallet_transactions(wallet: str, page: int = 1) -> list[dict]:
    """Fetch transaction history for a wallet from Polygonscan."""
    if not config.POLYGONSCAN_API_KEY:
        log.warning("POLYGONSCAN_API_KEY not set — skipping on-chain lookup for %s", wallet[:10])
        return []

    params = {
        "module": "account",
        "action": "txlist",
        "address": wallet,
        "startblock": 0,
        "endblock": 99999999,
        "page": page,
        "offset": 100,
        "sort": "desc",
        "apikey": config.POLYGONSCAN_API_KEY,
    }
    data = _get(config.POLYGONSCAN_BASE_URL, params=params)
    if data and data.get("status") == "1":
        return data.get("result", [])
    return []


def fetch_token_transfers(wallet: str, page: int = 1) -> list[dict]:
    """Fetch ERC-20 token transfers for a wallet from Polygonscan."""
    if not config.POLYGONSCAN_API_KEY:
        return []

    params = {
        "module": "account",
        "action": "tokentx",
        "address": wallet,
        "startblock": 0,
        "endblock": 99999999,
        "page": page,
        "offset": 100,
        "sort": "desc",
        "apikey": config.POLYGONSCAN_API_KEY,
    }
    data = _get(config.POLYGONSCAN_BASE_URL, params=params)
    if data and data.get("status") == "1":
        return data.get("result", [])
    return []
