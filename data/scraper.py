from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import config
from data.models import Bet, Market

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory TTL cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[Any, float]] = {}

_TTL_MARKETS = 300    # 5 min  — active market lists
_TTL_PRICES = 60     # 1 min  — orderbook / price history
_TTL_TRADES = 300    # 5 min  — trade history per market
_TTL_HISTORY = 3600   # 1 hour — resolved markets, on-chain data


def _cache_get(key: str) -> Any:
    entry = _cache.get(key)
    if entry and time.monotonic() < entry[1]:
        log.debug("Cache hit: %s", key[:60])
        return entry[0]
    _cache.pop(key, None)
    return None


def _cache_set(key: str, data: Any, ttl: int) -> None:
    _cache[key] = (data, time.monotonic() + ttl)


def clear_scraper_cache() -> None:
    """Evict all cached API responses (e.g. after a forced refresh)."""
    _cache.clear()
    log.info("Scraper cache cleared")


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

    vol = raw.get("volumeNum") or float(raw.get("volume") or 0)
    try:
        vol = float(vol)
    except (TypeError, ValueError):
        vol = 0.0

    return Market(
        id=raw.get("conditionId") or raw.get("condition_id", ""),
        title=raw.get("question", ""),
        description=raw.get("description", ""),
        end_date=_parse_dt(end_date_str),
        resolved=resolved,
        outcome=outcome,
        created_at=_parse_dt(created_str),
        volume=vol,
    )


def fetch_markets(active_only: bool = True, limit: int = 100, max_pages: int = 50) -> list[Market]:
    """Fetch markets from the Gamma API with offset pagination."""
    key = f"markets:{active_only}:{limit}:{max_pages}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    markets: list[Market] = []
    offset = 0

    for page in range(max_pages):
        params: dict[str, Any] = {"limit": limit, "offset": offset,
                                  "order": "createdAt", "ascending": "false"}
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
    _cache_set(key, markets, _TTL_MARKETS)
    return markets


def _parse_clob_market(raw: dict) -> Market:
    """Parse a market from the CLOB API (has winner info on tokens)."""
    end_str = raw.get("end_date_iso", "")
    # Try multiple fields for created_at — accepting_order_timestamp is often
    # empty for old markets, so fall back to a date well before end_date
    created_str = (
        raw.get("accepting_order_timestamp")
        or raw.get("game_start_time")
        or ""
    )

    def _parse_dt(s: str) -> datetime | None:
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s).replace(tzinfo=None)
        except ValueError:
            return None

    tokens = raw.get("tokens", [])
    resolved = False
    outcome = None
    for i, tok in enumerate(tokens):
        if tok.get("winner"):
            resolved = True
            out = tok.get("outcome", "")
            if out.lower() in ("yes", "no"):
                outcome = out.upper()
            else:
                outcome = "YES" if i == 0 else "NO"
            break

    end_date = _parse_dt(end_str) or datetime.now(timezone.utc).replace(tzinfo=None)
    created_at = _parse_dt(created_str)
    if created_at is None or created_at > end_date:
        # Fallback: assume market ran for 30 days before end_date
        created_at = end_date - timedelta(days=30)
        log.warning("CLOB market %s missing created_at — using 30-day fallback (lifespan estimate unreliable)",
                    raw.get("condition_id", "?")[:16])

    return Market(
        id=raw.get("condition_id", ""),
        title=raw.get("question", ""),
        description=raw.get("description", ""),
        end_date=end_date,
        resolved=resolved,
        outcome=outcome,
        created_at=created_at,
    )


def fetch_resolved_markets(limit: int = 1000, max_pages: int = 10) -> list[Market]:
    """Fetch resolved/closed markets from the CLOB API (has winner data)."""
    key = f"resolved_markets:{max_pages}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

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
    _cache_set(key, markets, _TTL_HISTORY)
    return markets


# ---------------------------------------------------------------------------
# Data API — Public trade history (no auth needed)
# ---------------------------------------------------------------------------

def _parse_trade(raw: dict, condition_id: str) -> Bet:
    ts = raw.get("timestamp", 0)
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    else:
        dt = datetime.now(timezone.utc).replace(tzinfo=None)

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

    # Normalize odds to YES probability regardless of which token was traded.
    # API "price" is the execution price of the specific token (YES or NO).
    raw_price = float(raw.get("price", 0))
    if outcome.lower() == "no":
        yes_prob = 1.0 - raw_price      # NO token at $0.40 → YES prob = $0.60
    elif outcome.lower() == "yes":
        yes_prob = raw_price             # YES token at $0.60 → YES prob = $0.60
    else:
        # Multi-outcome: index 0 = YES token, index 1 = NO token
        yes_prob = (1.0 - raw_price) if outcome_index == 1 else raw_price

    return Bet(
        market_id=condition_id,
        wallet=raw.get("proxyWallet", ""),
        side=side,
        amount=float(raw.get("size", 0)),
        odds=max(0.0, min(1.0, yes_prob)),
        timestamp=dt,
    )


def fetch_trades_for_market(
    condition_id: str,
    limit: int = 500,
    max_pages: int = 7,
    since: datetime | None = None,
) -> list[Bet]:
    """Fetch public trades for a market from the Data API.
    API hard-caps at offset ~3500, so max_pages=7 at limit=500.
    Full fetches (since=None) are cached for 5 min."""
    if since is None:
        key = f"trades:{condition_id}:{limit}:{max_pages}"
        cached = _cache_get(key)
        if cached is not None:
            return cached

    data_api_url = "https://data-api.polymarket.com/trades"
    bets: list[Bet] = []
    offset = 0

    for page in range(max_pages):
        params: dict[str, Any] = {
            "market": condition_id,
            "limit": limit,
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
    if since is None:
        _cache_set(key, bets, _TTL_TRADES)
    return bets


def fetch_leaderboard(
    limit: int = 100,
    time_period: str = "ALL",
    order_by: str = "PNL",
) -> list[dict]:
    """Fetch top traders from the Data API leaderboard.

    Returns list of dicts with keys: address, volume, pnl.
    Used to seed the wallet tracking table with known sharp traders.
    Cache: 5 min (leaderboard changes slowly within a cycle).
    """
    key = f"leaderboard:{limit}:{time_period}:{order_by}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    url = "https://data-api.polymarket.com/v1/leaderboard"
    results: list[dict] = []
    offset = 0
    batch = min(limit, 50)  # API max per request = 50

    while len(results) < limit:
        params: dict[str, Any] = {
            "category": "OVERALL",
            "timePeriod": time_period,
            "orderBy": order_by,
            "limit": batch,
            "offset": offset,
        }
        try:
            data = _get(url, params=params)
        except requests.RequestException:
            log.warning("Leaderboard fetch failed at offset %d", offset)
            break

        if not data:
            break

        for entry in data:
            addr = entry.get("proxyWallet", "")
            if addr:
                results.append({
                    "address": addr,
                    "volume": float(entry.get("vol") or 0),
                    "pnl": float(entry.get("pnl") or 0),
                })

        if len(data) < batch:
            break
        offset += batch

    log.info("Leaderboard: fetched %d wallets (period=%s, order=%s)", len(results), time_period, order_by)
    _cache_set(key, results, _TTL_MARKETS)
    return results
