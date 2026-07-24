"""Tests for news-sentiment wiring in the CRO debate protocol.

The fundamental_context gate already collects VADER-scored news sentiment
into ``evidence["news"]``. ``run_debate`` should surface that as:
  1. a weight-0 camp member (source="news") in the right camp, and
  2. a ``news_sentiment`` payload in ``to_dict()`` for the UI panel.
"""

from __future__ import annotations

from app.engine.confluence import ScenarioFrame
from app.engine.debate import run_debate

SCENARIO = ScenarioFrame(
    primary="range continuation",
    alternative="breakout",
    invalidation="loss of support",
)

BULLISH_NEWS = {
    "sentiment_label": "bullish",
    "mean_compound": 0.25,
    "bullish": 4,
    "bearish": 1,
    "total_articles": 7,
    "macro_label": "neutral",
    "macro_compound": 0.0,
    "top_headlines": ["Bitcoin ETF inflows accelerate", "BTC breaks resistance", "Rally ahead"],
}

BEARISH_NEWS = {
    "sentiment_label": "bearish",
    "mean_compound": -0.3,
    "bullish": 0,
    "bearish": 5,
    "total_articles": 5,
    "macro_label": "bearish",
    "macro_compound": -0.1,
    "top_headlines": ["Exchange hack spooks market"],
}


def test_news_sentiment_bullish_joins_bull_camp():
    result = run_debate([], SCENARIO, news_sentiment=BULLISH_NEWS)

    members = [m for m in result.bull_camp.members if m.source == "news"]
    assert len(members) == 1
    member = members[0]
    assert member.direction == 1
    assert member.weight == 0.0  # informational, not scored
    assert member.name == "news_sentiment"
    assert "4" in member.reasoning and "bullish" in member.reasoning.lower()


def test_news_sentiment_bearish_joins_bear_camp():
    result = run_debate([], SCENARIO, news_sentiment=BEARISH_NEWS)

    assert [m for m in result.bull_camp.members if m.source == "news"] == []
    members = [m for m in result.bear_camp.members if m.source == "news"]
    assert len(members) == 1
    assert members[0].direction == -1


def test_news_sentiment_neutral_joins_neutral_camp():
    neutral_news = dict(BULLISH_NEWS, sentiment_label="neutral", mean_compound=0.0,
                        bullish=2, bearish=2)
    result = run_debate([], SCENARIO, news_sentiment=neutral_news)

    assert [m for m in result.neutral_camp.members if m.source == "news"]


def test_news_sentiment_error_payload_excluded():
    result = run_debate([], SCENARIO, news_sentiment={"error": "boom"})

    for camp in (result.bull_camp, result.bear_camp, result.neutral_camp):
        assert [m for m in camp.members if m.source == "news"] == []
    assert result.to_dict().get("news_sentiment") is None


def test_news_sentiment_zero_articles_excluded():
    empty = dict(BULLISH_NEWS, total_articles=0, bullish=0, bearish=0)
    result = run_debate([], SCENARIO, news_sentiment=empty)

    for camp in (result.bull_camp, result.bear_camp, result.neutral_camp):
        assert [m for m in camp.members if m.source == "news"] == []
    assert result.to_dict().get("news_sentiment") is None


def test_to_dict_includes_news_payload_for_ui():
    result = run_debate([], SCENARIO, news_sentiment=BULLISH_NEWS)

    payload = result.to_dict()["news_sentiment"]
    assert payload["sentiment_label"] == "bullish"
    assert payload["bullish"] == 4
    assert payload["bearish"] == 1
    assert payload["total_articles"] == 7
    assert payload["top_headlines"][0] == "Bitcoin ETF inflows accelerate"


def test_without_news_to_dict_stays_backward_compatible():
    result = run_debate([], SCENARIO)

    assert result.to_dict().get("news_sentiment") is None
