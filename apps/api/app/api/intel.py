"""Token safety + trenches + smart wallet API — free public APIs, no keys.

Sources:
  * GoPlus Labs — honeypot/rug detection (free, no key)
  * DEX Screener — trending pairs, new listings, volume (free, no key)
  * CoinGecko — trending coins, Fear & Greed (free, no key)
  * blockchain.info — large BTC transactions (free, no key)
  * alternative.me — Fear & Greed index (free, no key)
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/intel", tags=["intel"])

GOPLUS = "https://api.gopluslabs.io/api/v1"
DEXSCREENER = "https://api.dexscreener.com"
COINGECKO = "https://api.coingecko.com/api/v3"
FNG = "https://api.alternative.me/fng"
BLOCKCHAIN_INFO = "https://blockchain.info"
TIMEOUT = 12.0


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, verify=False,
                             headers={"User-Agent": "confluence-trading-consultant/1.0"})


# ── Token Safety ──────────────────────────────────────────────

class TokenSafetyOut(BaseModel):
    address: str
    chain_id: int
    is_honeypot: bool | None = None
    buy_tax: float | None = None
    sell_tax: float | None = None
    is_mintable: bool | None = None
    can_take_back_ownership: bool | None = None
    owner_change_balance: bool | None = None
    is_proxy: bool | None = None
    holder_count: int | None = None
    total_supply: float | None = None
    lp_holders_count: int | None = None
    is_open_source: bool | None = None
    is_blacklisted: bool | None = None
    slippage_modifiable: bool | None = None
    risk_level: str = "unknown"  # safe / caution / danger / unknown
    risk_flags: list[str] = []
    source: str = "goplus"


def _bool(v: Any) -> bool | None:
    if v is None:
        return None
    return str(v) == "1"


def _assess_risk(d: dict) -> tuple[str, list[str]]:
    flags: list[str] = []
    if _bool(d.get("is_honeypot")):
        flags.append("HONEYPOT")
    if _bool(d.get("is_mintable")):
        flags.append("MINTABLE")
    if _bool(d.get("can_take_back_ownership")):
        flags.append("OWNERSHIP_TAKEBACK")
    if _bool(d.get("owner_change_balance")):
        flags.append("OWNER_CAN_CHANGE_BALANCE")
    if _bool(d.get("slippage_modifiable")):
        flags.append("SLIPPAGE_MODIFIABLE")
    if _bool(d.get("is_blacklisted")):
        flags.append("BLACKLIST_FUNCTION")
    if not _bool(d.get("is_open_source")):
        flags.append("NOT_OPEN_SOURCE")
    buy_tax = float(d.get("buy_tax") or 0)
    sell_tax = float(d.get("sell_tax") or 0)
    if buy_tax > 0.1 or sell_tax > 0.1:
        flags.append(f"HIGH_TAX(buy={buy_tax:.0%},sell={sell_tax:.0%})")
    if not flags:
        return "safe", []
    if any(f in ("HONEYPOT", "OWNERSHIP_TAKEBACK", "OWNER_CAN_CHANGE_BALANCE") for f in flags):
        return "danger", flags
    return "caution", flags


@router.get("/token-safety", response_model=TokenSafetyOut)
async def token_safety(
    _user: Annotated[User, Depends(get_current_user)],
    address: str = Query(..., min_length=10),
    chain_id: int = Query(1, ge=1),
):
    """Analyze a token contract for honeypot/rug risks via GoPlus."""
    async with _client() as c:
        resp = await c.get(
            f"{GOPLUS}/token_security/{chain_id}",
            params={"contract_addresses": address},
        )
        if resp.status_code != 200:
            return TokenSafetyOut(address=address, chain_id=chain_id,
                                  risk_level="unknown", risk_flags=["API_ERROR"])
        data = resp.json()
        result = (data.get("result") or {}).get(address.lower()) or {}
        if not result:
            return TokenSafetyOut(address=address, chain_id=chain_id,
                                  risk_level="unknown", risk_flags=["NOT_FOUND"])

        risk_level, risk_flags = _assess_risk(result)
        return TokenSafetyOut(
            address=address,
            chain_id=chain_id,
            is_honeypot=_bool(result.get("is_honeypot")),
            buy_tax=float(result.get("buy_tax") or 0),
            sell_tax=float(result.get("sell_tax") or 0),
            is_mintable=_bool(result.get("is_mintable")),
            can_take_back_ownership=_bool(result.get("can_take_back_ownership")),
            owner_change_balance=_bool(result.get("owner_change_balance")),
            is_proxy=_bool(result.get("is_proxy")),
            holder_count=int(result.get("holder_count") or 0),
            total_supply=float(result.get("total_supply") or 0),
            lp_holders_count=int(result.get("lp_holders_count") or 0),
            is_open_source=_bool(result.get("is_open_source")),
            is_blacklisted=_bool(result.get("is_blacklisted")),
            slippage_modifiable=_bool(result.get("slippage_modifiable")),
            risk_level=risk_level,
            risk_flags=risk_flags,
        )


# ── Trenches / Opportunity Scanner ────────────────────────────

@router.get("/trenches")
async def trenches(
    _user: Annotated[User, Depends(get_current_user)],
    chain: str = Query("all"),
    hide_stable: bool = Query(True),
    sort: str = Query("volume"),
    limit: int = Query(20, ge=1, le=50),
):
    """Trending/new pairs from DEX Screener + CoinGecko trending coins."""
    out: dict[str, Any] = {"pairs": [], "trending_coins": [], "source": "dexscreener+coingecko"}
    _STABLES = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USDD", "PYUSD", "GUSD", "FRAX"}

    async with _client() as c:
        # DEX Screener — boosted / latest tokens
        try:
            url = f"{DEXSCREENER}/token-profiles/latest/v1"
            resp = await c.get(url)
            if resp.status_code == 200:
                profiles = resp.json()[:limit]
                for p in profiles:
                    out["pairs"].append({
                        "chain": p.get("chainId", "?"),
                        "dex": p.get("dexId", "?"),
                        "token_address": p.get("tokenAddress", ""),
                        "url": p.get("url", ""),
                        "description": (p.get("description") or "")[:120],
                        "icon": p.get("icon", ""),
                        "source": "dexscreener_profiles",
                    })
        except Exception as exc:
            logger.debug("dexscreener profiles: %s", exc)

        # DEX Screener — search by volume (top pairs)
        try:
            resp2 = await c.get(f"{DEXSCREENER}/latest/dex/search", params={"q": "USDT"})
            if resp2.status_code == 200:
                pairs = (resp2.json() or {}).get("pairs") or []
                # Sort by volume
                pairs.sort(key=lambda p: float(p.get("volume", {}).get("h24", 0) or 0), reverse=True)
                for p in pairs[:limit]:
                    vol = p.get("volume", {})
                    price_change = p.get("priceChange", {})
                    out["pairs"].append({
                        "chain": p.get("chainId", "?"),
                        "dex": p.get("dexId", "?"),
                        "pair_address": p.get("pairAddress", ""),
                        "base_token": p.get("baseToken", {}).get("symbol", "?"),
                        "quote_token": p.get("quoteToken", {}).get("symbol", "?"),
                        "price_usd": float(p.get("priceUsd", 0) or 0),
                        "volume_24h": float(vol.get("h24", 0) or 0),
                        "volume_6h": float(vol.get("h6", 0) or 0),
                        "volume_1h": float(vol.get("h1", 0) or 0),
                        "price_change_24h": float(price_change.get("h24", 0) or 0),
                        "price_change_6h": float(price_change.get("h6", 0) or 0),
                        "liquidity_usd": float((p.get("liquidity") or {}).get("usd", 0) or 0),
                        "fdv": float(p.get("fdv", 0) or 0),
                        "pair_created_at": p.get("pairCreatedAt"),
                        "url": p.get("url", ""),
                        "source": "dexscreener_search",
                    })
        except Exception as exc:
            logger.debug("dexscreener search: %s", exc)

        # CoinGecko trending
        try:
            resp3 = await c.get(f"{COINGECKO}/search/trending")
            if resp3.status_code == 200:
                coins = (resp3.json() or {}).get("coins") or []
                for item in coins[:10]:
                    c_data = item.get("item", {})
                    out["trending_coins"].append({
                        "name": c_data.get("name", "?"),
                        "symbol": c_data.get("symbol", "?"),
                        "market_cap_rank": c_data.get("market_cap_rank"),
                        "price_btc": c_data.get("price_btc"),
                        "score": c_data.get("score"),
                        "thumb": c_data.get("thumb", ""),
                        "source": "coingecko_trending",
                    })
        except Exception as exc:
            logger.debug("coingecko trending: %s", exc)

    # Apply chain + stable filters
    if chain != "all":
        out["pairs"] = [p for p in out["pairs"] if p.get("chain") == chain]
    if hide_stable:
        out["pairs"] = [p for p in out["pairs"]
                        if not (p.get("base_token", "").upper() in _STABLES
                                and p.get("quote_token", "").upper() in _STABLES)]

    return out


# ── Smart Wallet / Whale Tracker ──────────────────────────────

@router.get("/whale-movements")
async def whale_movements(
    _user: Annotated[User, Depends(get_current_user)],
    min_btc: float = Query(100, ge=1),
    limit: int = Query(20, ge=1, le=50),
):
    """Large BTC transactions from blockchain.info (free, no key)."""
    out: list[dict[str, Any]] = []
    try:
        async with _client() as c:
            resp = await c.get(f"{BLOCKCHAIN_INFO}/latestblock")
            if resp.status_code != 200:
                return {"movements": [], "source": "blockchain.info", "error": "API unavailable"}
            block = resp.json()
            block_hash = block.get("hash", "")
            if not block_hash:
                return {"movements": [], "source": "blockchain.info"}

            resp2 = await c.get(f"{BLOCKCHAIN_INFO}/rawblock/{block_hash}", params={"limit": "50"})
            if resp2.status_code != 200:
                return {"movements": [], "source": "blockchain.info"}
            txs = (resp2.json() or {}).get("tx", [])

            for tx in txs[:200]:
                total_out = sum(o.get("value", 0) for o in tx.get("out", [])) / 1e8
                if total_out >= min_btc:
                    out.append({
                        "tx_hash": tx.get("hash", ""),
                        "btc_amount": round(total_out, 4),
                        "usd_estimate": round(total_out * 66000, 0),  # rough
                        "inputs": len(tx.get("inputs", [])),
                        "outputs": len(tx.get("out", [])),
                        "time": tx.get("time"),
                        "source": "blockchain.info",
                    })
                if len(out) >= limit:
                    break
    except Exception as exc:
        logger.debug("whale movements: %s", exc)

    out.sort(key=lambda x: -x["btc_amount"])
    return {"movements": out, "count": len(out), "source": "blockchain.info"}


# ── Market Sentiment ──────────────────────────────────────────

@router.get("/sentiment")
async def market_sentiment(_user: Annotated[User, Depends(get_current_user)]):
    """Fear & Greed index from alternative.me (free, no key)."""
    try:
        async with _client() as c:
            resp = await c.get(FNG, params={"limit": "7"})
            if resp.status_code == 200:
                data = resp.json()
                entries = data.get("data", [])
                return {
                    "current": entries[0] if entries else None,
                    "history": entries,
                    "source": "alternative.me",
                }
    except Exception as exc:
        logger.debug("sentiment: %s", exc)
    return {"current": None, "history": [], "source": "alternative.me"}
