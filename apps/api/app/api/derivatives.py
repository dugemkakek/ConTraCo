"""Derivatives + charting signals + council wallet analyzer API."""
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.db.models import User
from app.services.market_data.cg_cache import cached_get
from app.services.market_data.derivatives import (
    get_funding_history,
    get_liquidation_heatmap,
    get_open_interest_history,
)
from app.services.market_data.signals import generate_pinescript, get_trade_signals
from app.services.onchain.multi_chain_wallet import analyze_wallet_multi_chain

router = APIRouter(prefix="/api/v1", tags=["derivatives-charting"])

CG = "https://api.coingecko.com/api/v3"


@router.get("/derivatives/funding")
async def funding(
    _user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query("BTCUSDT"),
    limit: int = Query(100, ge=10, le=500),
):
    return await get_funding_history(symbol=symbol, limit=limit)


@router.get("/derivatives/open-interest")
async def open_interest(
    _user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query("BTCUSDT"),
    period: str = Query("5m"),
    limit: int = Query(100, ge=10, le=500),
):
    return await get_open_interest_history(symbol=symbol, period=period, limit=limit)


@router.get("/derivatives/liquidation-heatmap")
async def liquidation_heatmap(
    _user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("1h"),
    limit: int = Query(240, ge=50, le=500),
    bins: int = Query(40, ge=10, le=100),
):
    return await get_liquidation_heatmap(symbol=symbol, interval=interval, limit=limit, bins=bins)


@router.get("/charting/signals")
async def signals(
    _user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("1h"),
    limit: int = Query(300, ge=100, le=1000),
):
    return await get_trade_signals(symbol=symbol, interval=interval, limit=limit)


@router.get("/charting/pinescript")
async def pinescript(_user: Annotated[User, Depends(get_current_user)]):
    return {"name": "ConTraCo EMA RSI ATR Signals", "script": generate_pinescript()}


@router.get("/arbitrage/scan")
async def arbitrage_scan(
    _user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query("BTC"),
    min_volume: float = Query(10000, ge=0),
):
    """Cross-market arbitrage for one asset across all CoinGecko-listed exchanges."""
    q = symbol.lower().replace("/usdt", "")
    async with httpx.AsyncClient(timeout=20, verify=False) as c:
        try:
            search = (await cached_get(c, f"{CG}/search", params={"query": q})).json()
            coins = search.get("coins", [])
            match = next((x for x in coins if x.get("symbol", "").lower() == q), None)
            if not match:
                return {"symbol": symbol.upper(), "markets": [], "opportunities": [], "error": "symbol not found"}
            coin_id = match["id"]
            tickers = (await cached_get(c, f"{CG}/coins/{coin_id}/tickers",
                                        params={"page": 1, "include_exchange_logo": "false"})).json()
        except Exception as exc:
            raise HTTPException(502, f"coingecko unavailable: {exc}")

    rows = []
    for t in tickers.get("tickers", []):
        last = float(t.get("last") or 0)
        volume = float(t.get("volume") or 0)
        target = (t.get("target") or "").upper()
        if last <= 0 or volume < min_volume or target not in {"USD", "USDT", "USDC"}:
            continue
        rows.append({
            "exchange": t.get("market", {}).get("name", "unknown"),
            "base": (t.get("base") or "").upper(),
            "target": target,
            "last": last,
            "volume": volume,
            "trust_score": t.get("trust_score"),
            "trade_url": t.get("trade_url"),
        })

    opps: list[dict[str, Any]] = []
    if len(rows) >= 2:
        rows.sort(key=lambda x: x["last"])
        low, high = rows[0], rows[-1]
        gross = ((high["last"] - low["last"]) / low["last"]) * 100 if low["last"] else 0
        net = gross - 0.35
        if net > 0:
            opps.append({
                "buy_exchange": low["exchange"], "buy_price": low["last"],
                "sell_exchange": high["exchange"], "sell_price": high["last"],
                "gross_spread_pct": round(gross, 4), "net_spread_pct_est": round(net, 4),
            })

    return {"symbol": symbol.upper(), "coin_id": coin_id, "markets": rows[:50],
            "opportunities": opps, "source": "coingecko"}


@router.get("/council/wallets/{address}/analyze")
async def council_wallet(
    address: str,
    _user: Annotated[User, Depends(get_current_user)],
    chains: str = Query("eth,base,arbitrum,optimism,polygon"),
):
    if not address.startswith("0x") or len(address) != 42:
        raise HTTPException(400, "address must be 0x-prefixed 20-byte hex")
    return await analyze_wallet_multi_chain(
        address, [c.strip() for c in chains.split(",") if c.strip()])
