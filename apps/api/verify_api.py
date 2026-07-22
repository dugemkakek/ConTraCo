#!/usr/bin/env python3
"""ConTraCo API Verification Script.

Tests all public (no-auth) endpoints against a running ConTraCo API server.
Use this to confirm the API is healthy after deploy or changes.

Usage:
  # Default: localhost:8000
  python verify_api.py

  # Custom host
  BASE_URL=http://your-server:8000 python verify_api.py

  # Against a live public deployment
  BASE_URL=https://api.yourapp.com python verify_api.py

Exit codes:
  0 = all checks passed
  1 = one or more checks failed
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 15.0
COLORS = sys.stdout.isatty()


def _green(s: str) -> str: return f"\033[32m{s}\033[0m" if COLORS else s
def _red(s: str) -> str: return f"\033[31m{s}\033[0m" if COLORS else s
def _yellow(s: str) -> str: return f"\033[33m{s}\033[0m" if COLORS else s
def _bold(s: str) -> str: return f"\033[1m{s}\033[0m" if COLORS else s


@dataclass
class CheckResult:
    name: str
    url: str
    passed: bool
    status_code: int | None = None
    latency_ms: float = 0.0
    error: str | None = None
    notes: list[str] = field(default_factory=list)


async def _get(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None = None,
    expected_keys: list[str] | None = None,
    expected_status: int = 200,
) -> CheckResult:
    url = f"{BASE_URL}{path}"
    t0 = time.monotonic()
    try:
        resp = await client.get(url, params=params, timeout=TIMEOUT)
        latency = (time.monotonic() - t0) * 1000
        body: Any = {}
        try:
            body = resp.json()
        except Exception:
            pass

        passed = resp.status_code == expected_status
        notes = []
        if expected_keys and isinstance(body, dict):
            for k in expected_keys:
                if k not in body:
                    notes.append(f"missing key: {k!r}")
                    passed = False

        return CheckResult(
            name=path,
            url=url,
            passed=passed,
            status_code=resp.status_code,
            latency_ms=round(latency, 1),
            notes=notes,
        )
    except httpx.ConnectError:
        return CheckResult(
            name=path, url=url, passed=False,
            error=f"Connection refused — is the API running at {BASE_URL}?"
        )
    except Exception as e:
        return CheckResult(name=path, url=url, passed=False, error=str(e))


EXISITNG_ENDPOINTS: list[dict] = [
    # ── Core ──────────────────────────────────────────────────────────────────
    {"path": "/health",                    "keys": ["status", "market_data_provider"]},
    {"path": "/docs",                      "keys": None, "expected_status": 200},
    {"path": "/openapi.json",              "keys": ["openapi", "paths"]},

    # ── Market data ───────────────────────────────────────────────────────────
    {"path": "/api/v1/market/candles",     "params": {"symbol": "BTCUSDT", "interval": "1h", "limit": 5}, "keys": ["candles"]},
    {"path": "/api/v1/market/ticker",      "params": {"symbol": "BTCUSDT"}, "keys": ["symbol"]},

    # ── Symbols ───────────────────────────────────────────────────────────────
    {"path": "/api/v1/symbols",            "keys": None},

    # ── DEX (existing) ────────────────────────────────────────────────────────
    {"path": "/api/v1/dex/networks",       "keys": ["networks"]},
    {"path": "/api/v1/dex/pools/top",      "params": {"network": "ethereum", "limit": 3}, "keys": ["pools"]},
    {"path": "/api/v1/dex/overview",       "keys": ["networks"]},

    # ── Fundamentals free ─────────────────────────────────────────────────────
    {"path": "/api/v1/fundamentals/free/fear-and-greed", "keys": None},
    {"path": "/api/v1/fundamentals/free/defillama/top",  "params": {"limit": 5}, "keys": None},

    # ── Sentiment / Macro ─────────────────────────────────────────────────────
    {"path": "/api/v1/sentiment/BTC",      "keys": None},
    {"path": "/api/v1/macro/snapshot",     "keys": None},

    # ── NEW: DEX Sniping ──────────────────────────────────────────────────────
    {"path": "/api/v1/dex/snipe/new-pools",  "params": {"network": "ethereum", "minutes_back": 60, "limit": 5}, "keys": ["pools"]},
    {"path": "/api/v1/dex/snipe/trending",   "params": {"network": "ethereum", "limit": 5}, "keys": ["pools"]},
    {"path": "/api/v1/dex/snipe/scan",       "params": {"networks": "ethereum,base", "minutes_back": 30}, "keys": ["pools"]},

    # ── NEW: DEX Tranche Intelligence ─────────────────────────────────────────
    {"path": "/api/v1/dex/tranches/analyze",      "params": {"network": "ethereum", "volatility": "medium"}, "keys": ["top_tranches"]},
    {"path": "/api/v1/dex/tranches/leaderboard",  "params": {"networks": "ethereum,base"}, "keys": ["leaderboard"]},
]


async def run_checks() -> int:
    print(_bold(f"\nConTraCo API Verify — {BASE_URL}"))
    print("=" * 60)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            _get(
                client,
                ep["path"],
                params=ep.get("params"),
                expected_keys=ep.get("keys"),
                expected_status=ep.get("expected_status", 200),
            )
            for ep in EXISITNG_ENDPOINTS
        ]
        results: list[CheckResult] = await asyncio.gather(*tasks)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    for r in results:
        icon = _green("✓") if r.passed else _red("✗")
        status = f"[{r.status_code}]" if r.status_code else ""
        latency = f"{r.latency_ms}ms" if r.latency_ms else ""
        notes = " — " + "; ".join(r.notes) if r.notes else ""
        err = f" — {r.error}" if r.error else ""
        print(f"  {icon} {r.name:<52} {status:>6}  {latency:>8}{notes}{err}")

    print("=" * 60)
    if failed == 0:
        print(_green(f"\n  All {passed} checks passed ✓\n"))
    else:
        print(_red(f"\n  {failed} failed, {passed} passed\n"))
        print(_yellow("  Tip: Check that the API is running and .env is configured."))
        print(_yellow(f"  Start with: cd apps/api && uvicorn app.main:app --reload\n"))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_checks()))
