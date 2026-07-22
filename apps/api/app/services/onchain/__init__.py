"""On-chain flow data via free public APIs (no key required).

Sources:
  * CoinGecko /coins/{id} — exchange tickers, volume distribution
  * blockchain.info — BTC network stats (hash rate, mempool, tx count)
  * Blockchair — chain stats for multiple networks (free tier)

All endpoints are free, no API key, CORS-friendly.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = float(os.getenv("FREE_PROVIDER_TIMEOUT", "8.0"))
USER_AGENT = "confluence-trading-consultant/1.0"

# CoinGecko id mapping for common symbols
COINGECKO_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "MATIC": "matic-network",
    "ARB": "arbitrum",
    "OP": "optimism",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "AAVE": "aave",
    "LTC": "litecoin",
    "TRX": "tron",
}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


async def get_onchain_metrics(symbol: str) -> dict[str, Any] | None:
    """Fetch real on-chain proxy metrics for a symbol.

    Returns dict with:
      - exchange_volume_24h_usd: total exchange volume
      - top_exchange_share_pct: % of volume on largest exchange (concentration)
      - exchange_count: number of exchanges listing the pair
      - price_change_24h_pct: 24h price change (momentum proxy)
      - market_cap_rank: global rank
      - source: data source identifier

    Returns None if the symbol is not supported or all fetches fail.
    """
    base = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()
    cg_id = COINGECKO_IDS.get(base)
    if not cg_id:
        return None

    async with _client() as client:
        try:
            resp = await client.get(
                f"https://api.coingecko.com/api/v3/coins/{cg_id}",
                params={
                    "localization": "false",
                    "tickers": "true",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
            if resp.status_code != 200:
                logger.warning("CoinGecko %s returned %d", cg_id, resp.status_code)
                return None

            data = resp.json()
            market = data.get("market_data", {})
            tickers = data.get("tickers", [])

            # Exchange concentration: what % of volume sits on the top exchange?
            exchange_volumes: dict[str, float] = {}
            for t in tickers:
                exch = (t.get("market") or {}).get("name", "unknown")
                vol_usd = float(t.get("converted_volume", {}).get("usd", 0) or 0)
                exchange_volumes[exch] = exchange_volumes.get(exch, 0) + vol_usd

            total_vol = sum(exchange_volumes.values())
            top_share = (max(exchange_volumes.values()) / total_vol * 100) if total_vol > 0 else 0

            return {
                "exchange_volume_24h_usd": total_vol,
                "top_exchange_share_pct": round(top_share, 1),
                "exchange_count": len(exchange_volumes),
                "price_change_24h_pct": market.get("price_change_percentage_24h"),
                "market_cap_rank": data.get("market_cap_rank"),
                "high_24h": market.get("high_24h", {}).get("usd"),
                "low_24h": market.get("low_24h", {}).get("usd"),
                "ath": market.get("ath", {}).get("usd"),
                "ath_change_pct": market.get("ath_change_percentage", {}).get("usd"),
                "circulating_supply": market.get("circulating_supply"),
                "total_supply": market.get("total_supply"),
                "source": "coingecko",
            }
        except Exception as exc:
            logger.warning("CoinGecko fetch failed for %s: %s", cg_id, exc)
            return None


async def get_btc_network_stats() -> dict[str, Any] | None:
    """BTC-specific on-chain stats from blockchain.info (free, no key)."""
    async with _client() as client:
        try:
            resp = await client.get("https://api.blockchain.info/stats")
            if resp.status_code != 200:
                return None
            data = resp.json()
            return {
                "hash_rate_ths": data.get("hash_rate"),
                "difficulty": data.get("difficulty"),
                "mempool_size": data.get("n_tx"),
                "miners_revenue_btc": data.get("miners_revenue_btc"),
                "estimated_tx_volume_usd": data.get("estimated_transaction_volume_usd"),
                "source": "blockchain.info",
            }
        except Exception as exc:
            logger.warning("blockchain.info fetch failed: %s", exc)
            return None
