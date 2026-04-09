from __future__ import annotations

from datetime import datetime

from briefing.llm.prompts import build_cluster_prompt, build_neutralize_prompt
from briefing.schemas import NewsItem


def _make_items():
    return [
        NewsItem(
            title="Apple beats earnings",
            source="Reuters",
            url="https://reuters.com/1",
            published_at=datetime(2026, 4, 10),
            snippet="Apple reported record Q2 earnings.",
            related_tickers=["AAPL"],
        ),
        NewsItem(
            title="Apple Q2 results strong",
            source="Bloomberg",
            url="https://bloomberg.com/1",
            published_at=datetime(2026, 4, 10),
            snippet="Strong performance in services.",
            related_tickers=["AAPL"],
        ),
    ]


class TestBuildClusterPrompt:
    def test_includes_all_articles(self):
        prompt = build_cluster_prompt(_make_items())
        assert "[0]" in prompt
        assert "[1]" in prompt
        assert "Apple beats earnings" in prompt
        assert "Apple Q2 results strong" in prompt

    def test_includes_source(self):
        prompt = build_cluster_prompt(_make_items())
        assert "Reuters" in prompt
        assert "Bloomberg" in prompt


class TestBuildNeutralizePrompt:
    def test_basic_prompt(self):
        prompt = build_neutralize_prompt(_make_items())
        assert "neutral summary" in prompt.lower() or "neutral" in prompt.lower()
        assert "Apple beats earnings" in prompt

    def test_with_tickers_includes_sentiment_instructions(self):
        prompt = build_neutralize_prompt(_make_items(), related_tickers=["AAPL", "MSFT"])
        assert "AAPL" in prompt
        assert "MSFT" in prompt
        assert "ticker_sentiments" in prompt
        assert "sentiment" in prompt

    def test_without_tickers_no_sentiment(self):
        prompt = build_neutralize_prompt(_make_items(), related_tickers=None)
        assert "ticker_sentiments" not in prompt

    def test_empty_tickers_no_sentiment(self):
        prompt = build_neutralize_prompt(_make_items(), related_tickers=[])
        assert "ticker_sentiments" not in prompt
