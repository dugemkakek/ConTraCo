"""Pure-Python technical indicators.

Each function takes a list[OHLCV] (any object with .open/.high/.low/
.close/.volume — Pydantic ``Candle`` qualifies) and returns a list
aligned by index. For warmup bars the value is ``None``-friendly
(filled with the seed) so downstream code can index without checks.

These are intentionally small and dependency-free so the analysis
engine can be unit-tested without numpy.
"""

from __future__ import annotations

import math
from typing import Iterable, Protocol


class _Bar(Protocol):
    open: float
    high: float
    low: float
    close: float
    volume: float


def ema(values: Iterable[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    out: list[float] = []
    prev: float | None = None
    for v in values:
        if prev is None:
            prev = v
            out.append(v)
        else:
            prev = v * k + prev * (1 - k)
            out.append(prev)
    return out


def sma(values: Iterable[float], period: int) -> list[float]:
    vals = list(values)
    out: list[float] = []
    window: list[float] = []
    running = 0.0
    for v in vals:
        window.append(v)
        running += v
        if len(window) > period:
            running -= window.pop(0)
        out.append(running / len(window))
    return out


def rsi(closes: Iterable[float], period: int = 14) -> list[float]:
    """Wilder's RSI. First ``period`` bars are seeded with 50 (neutral)."""
    closes = list(closes)
    out: list[float] = []
    gains: list[float] = []
    losses: list[float] = []
    avg_gain = 0.0
    avg_loss = 0.0
    for i, c in enumerate(closes):
        if i == 0:
            out.append(50.0)
            continue
        change = c - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        gains.append(gain)
        losses.append(loss)
        if len(gains) < period:
            out.append(50.0)
            continue
        if len(gains) == period:
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
        else:
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out.append(100.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100.0 - (100.0 / (1.0 + rs)))
    return out


def macd(closes: Iterable[float], fast: int = 12, slow: int = 26, signal: int = 9):
    closes = list(closes)
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = ema(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, hist


def atr(bars: Iterable[_Bar], period: int = 14) -> list[float]:
    bars = list(bars)
    out: list[float] = []
    prev_close: float | None = None
    trs: list[float] = []
    running = 0.0
    for b in bars:
        if prev_close is None:
            tr = b.high - b.low
        else:
            tr = max(b.high - b.low, abs(b.high - prev_close), abs(b.low - prev_close))
        trs.append(tr)
        running += tr
        if len(trs) > period:
            running -= trs.pop(0)
        out.append(running / len(trs))
        prev_close = b.close
    return out


def adx(bars: Iterable[_Bar], period: int = 14) -> list[float]:
    """Welles Wilder ADX. Returns the ADX; +DI/-DI are in the helper."""
    bars = list(bars)
    if len(bars) < period * 2:
        return [20.0] * len(bars)
    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    trs: list[float] = []
    for i in range(1, len(bars)):
        up = bars[i].high - bars[i - 1].high
        down = bars[i - 1].low - bars[i].low
        plus_dm.append(max(up, 0.0) if up > down and up > 0 else 0.0)
        minus_dm.append(max(down, 0.0) if down > up and down > 0 else 0.0)
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
        trs.append(tr)
    # smooth
    def smooth(seq):
        s = sum(seq[:period])
        out = [s]
        for v in seq[period:]:
            s = s - s / period + v
            out.append(s)
        return out

    tr_n = smooth(trs)
    plus_dm_n = smooth(plus_dm[1:])
    minus_dm_n = smooth(minus_dm[1:])
    plus_di = [100 * dm / tr if tr else 0 for dm, tr in zip(plus_dm_n, tr_n)]
    minus_di = [100 * dm / tr if tr else 0 for dm, tr in zip(minus_dm_n, tr_n)]
    dx = [
        100 * abs(p - m) / (p + m) if (p + m) else 0
        for p, m in zip(plus_di, minus_di)
    ]
    adx_vals = smooth(dx)
    # pad the head to align length
    head = len(bars) - len(adx_vals)
    return ([20.0] * head) + adx_vals


def bollinger(closes: Iterable[float], period: int = 20, mult: float = 2.0):
    """Returns (middle, upper, lower, percent_b)."""
    closes = list(closes)
    mid = sma(closes, period)
    upper: list[float] = []
    lower: list[float] = []
    pb: list[float] = []
    window: list[float] = []
    for i, c in enumerate(closes):
        window.append(c)
        if len(window) > period:
            window.pop(0)
        m = sum(window) / len(window)
        var = sum((x - m) ** 2 for x in window) / len(window)
        sd = math.sqrt(var)
        u = m + mult * sd
        l = m - mult * sd
        upper.append(u)
        lower.append(l)
        pb.append((c - l) / (u - l) if u != l else 0.5)
    return mid, upper, lower, pb


def obv(bars: Iterable[_Bar]) -> list[float]:
    bars = list(bars)
    out: list[float] = [0.0]
    for i in range(1, len(bars)):
        prev = bars[i - 1]
        cur = bars[i]
        if cur.close > prev.close:
            out.append(out[-1] + cur.volume)
        elif cur.close < prev.close:
            out.append(out[-1] - cur.volume)
        else:
            out.append(out[-1])
    return out


def swing_highs_lows(bars: Iterable[_Bar], lookback: int = 3):
    """Return (swing_highs, swing_lows) as dicts {index: price}."""
    bars = list(bars)
    highs: dict[int, float] = {}
    lows: dict[int, float] = {}
    for i in range(lookback, len(bars) - lookback):
        center_high = bars[i].high
        center_low = bars[i].low
        is_high = all(
            center_high > bars[i + j].high and center_high > bars[i - j].high
            for j in range(1, lookback + 1)
        )
        is_low = all(
            center_low < bars[i + j].low and center_low < bars[i - j].low
            for j in range(1, lookback + 1)
        )
        if is_high:
            highs[i] = center_high
        if is_low:
            lows[i] = center_low
    return highs, lows


__all__ = [
    "ema",
    "sma",
    "rsi",
    "macd",
    "atr",
    "adx",
    "bollinger",
    "obv",
    "swing_highs_lows",
]
