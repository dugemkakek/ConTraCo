import type { Candle } from "./api";

export function computeEMA(candles: Candle[], period: number): number[] {
  const k = 2 / (period + 1);
  const ema: number[] = [];
  candles.forEach((c, i) => {
    if (i === 0) {
      ema.push(c.close);
    } else {
      ema.push(c.close * k + ema[i - 1] * (1 - k));
    }
  });
  return ema;
}
