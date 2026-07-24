"""Trade signal generation — EMA cross + RSI filter + ATR-based TP/SL.

Uses Binance vision klines (works in geo-blocked regions). Also emits a
matching PineScript v5 strategy so the user can paste it into TradingView.
"""
from __future__ import annotations

from typing import Any

from app.services.market_data.derivatives import _get_klines


def ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values: list[float], period: int = 14) -> list[float]:
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    out = [50.0] * len(values)
    for i in range(period, len(values)):
        avg_gain = sum(gains[i - period + 1:i + 1]) / period
        avg_loss = sum(losses[i - period + 1:i + 1]) / period
        rs = avg_gain / avg_loss if avg_loss else 999
        out[i] = 100 - (100 / (1 + rs))
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    out = []
    for i in range(len(trs)):
        start = max(0, i - period + 1)
        out.append(sum(trs[start:i + 1]) / len(trs[start:i + 1]))
    return out


async def get_trade_signals(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 300) -> dict[str, Any]:
    candles = await _get_klines(symbol=symbol, interval=interval, limit=limit)
    if not candles:
        return {"symbol": symbol.upper(), "interval": interval, "signals": [], "candles": [],
                "source": "unavailable"}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    fast = ema(closes, 9)
    slow = ema(closes, 21)
    rsis = rsi(closes, 14)
    atrs = atr(highs, lows, closes, 14)

    signals = []
    for i in range(1, len(closes)):
        buy = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i] and rsis[i] > 52
        sell = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i] and rsis[i] < 48
        if not (buy or sell):
            continue

        entry = closes[i]
        a = atrs[i]
        side = "buy" if buy else "sell"
        sl = entry - 1.5 * a if buy else entry + 1.5 * a
        tp1 = entry + 2.0 * a if buy else entry - 2.0 * a
        tp2 = entry + 3.5 * a if buy else entry - 3.5 * a

        signals.append({
            "time": candles[i]["time"],
            "side": side,
            "entry": round(entry, 4),
            "stop_loss": round(sl, 4),
            "take_profit_1": round(tp1, 4),
            "take_profit_2": round(tp2, 4),
            "ema_fast": round(fast[i], 4),
            "ema_slow": round(slow[i], 4),
            "rsi": round(rsis[i], 2),
        })

    return {
        "symbol": symbol.upper(), "interval": interval,
        "signals": signals[-50:], "candles": candles[-200:],
        "source": "binance-vision",
    }


def generate_pinescript() -> str:
    return """//@version=5
strategy("ConTraCo EMA RSI ATR Signals", overlay=true, initial_capital=10000)
fast = ta.ema(close, 9)
slow = ta.ema(close, 21)
r = ta.rsi(close, 14)
a = ta.atr(14)

longCond = ta.crossover(fast, slow) and r > 52
shortCond = ta.crossunder(fast, slow) and r < 48

longSL = close - 1.5 * a
longTP1 = close + 2.0 * a
longTP2 = close + 3.5 * a

shortSL = close + 1.5 * a
shortTP1 = close - 2.0 * a
shortTP2 = close - 3.5 * a

plot(fast, color=color.teal, title="EMA 9")
plot(slow, color=color.orange, title="EMA 21")

plotshape(longCond, title="BUY", style=shape.labelup, location=location.belowbar, color=color.lime, text="BUY")
plotshape(shortCond, title="SELL", style=shape.labeldown, location=location.abovebar, color=color.red, text="SELL")

if longCond
    strategy.entry("Long", strategy.long)
    strategy.exit("Long TP/SL", "Long", stop=longSL, limit=longTP1)

if shortCond
    strategy.entry("Short", strategy.short)
    strategy.exit("Short TP/SL", "Short", stop=shortSL, limit=shortTP1)
"""
