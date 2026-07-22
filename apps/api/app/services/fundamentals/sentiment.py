"""Sentiment analysis for financial news using VADER.

VADER (Valence Aware Dictionary and sEntiment Reasoner) is a lexicon
and rule-based sentiment tool specifically attuned to social media
and short text. Free, no API key, runs locally.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_analyzer = None


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def analyze_sentiment(text: str) -> dict[str, float]:
    """Return VADER scores: {neg, neu, pos, compound}.

    compound is the normalized composite score in [-1, +1].
    """
    if not text or not text.strip():
        return {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0}
    try:
        sia = _get_analyzer()
        return sia.polarity_scores(text)
    except Exception as exc:
        logger.debug("VADER failed: %s", exc)
        return {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0}


def classify_sentiment(compound: float) -> str:
    """Map compound score to a label."""
    if compound >= 0.05:
        return "bullish"
    elif compound <= -0.05:
        return "bearish"
    return "neutral"


def aggregate_sentiment(texts: list[str]) -> dict[str, Any]:
    """Aggregate sentiment across multiple texts.

    Returns:
      - mean_compound: average compound score
      - bullish_count / bearish_count / neutral_count
      - total: number of texts analyzed
      - label: overall classification
    """
    if not texts:
        return {
            "mean_compound": 0.0,
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "total": 0,
            "label": "neutral",
        }

    scores = [analyze_sentiment(t) for t in texts]
    compounds = [s["compound"] for s in scores]
    mean = sum(compounds) / len(compounds)

    bullish = sum(1 for c in compounds if c >= 0.05)
    bearish = sum(1 for c in compounds if c <= -0.05)
    neutral = len(compounds) - bullish - bearish

    return {
        "mean_compound": round(mean, 4),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "total": len(compounds),
        "label": classify_sentiment(mean),
    }
