from __future__ import annotations

from datetime import datetime

import pytest

from briefing.pipeline.news import _deduplicate, _fallback_grouping, neutralize_news
from briefing.schemas import NewsItem


def _make_item(title: str, url: str, tickers: list[str]) -> NewsItem:
    return NewsItem(
        title=title,
        source="TestSource",
        url=url,
        published_at=datetime(2026, 4, 10),
        snippet=f"Snippet for {title}",
        related_tickers=tickers,
    )


class TestDeduplicate:
    def test_removes_duplicate_urls(self):
        items = [
            _make_item("A", "https://a.com/1", ["AAPL"]),
            _make_item("A copy", "https://a.com/1", ["MSFT"]),
            _make_item("B", "https://b.com/2", ["AAPL"]),
        ]
        result = _deduplicate(items)
        assert len(result) == 2

    def test_merges_tickers_on_dedup(self):
        items = [
            _make_item("A", "https://a.com/1", ["AAPL"]),
            _make_item("A", "https://a.com/1", ["MSFT"]),
            _make_item("A", "https://a.com/1", ["AAPL", "GOOGL"]),
        ]
        result = _deduplicate(items)
        assert len(result) == 1
        assert set(result[0].related_tickers) == {"AAPL", "MSFT", "GOOGL"}

    def test_preserves_order(self):
        items = [
            _make_item("First", "https://a.com/1", ["AAPL"]),
            _make_item("Second", "https://b.com/2", ["MSFT"]),
            _make_item("Third", "https://c.com/3", ["GOOGL"]),
        ]
        result = _deduplicate(items)
        assert [r.title for r in result] == ["First", "Second", "Third"]

    def test_empty_input(self):
        assert _deduplicate([]) == []


class TestFallbackGrouping:
    def test_groups_by_ticker(self):
        items = [
            _make_item("A", "https://a.com/1", ["AAPL"]),
            _make_item("B", "https://b.com/2", ["AAPL"]),
            _make_item("C", "https://c.com/3", ["MSFT"]),
        ]
        stories = _fallback_grouping(items)
        tickers = {s.related_tickers[0] for s in stories}
        assert tickers == {"AAPL", "MSFT"}

    def test_no_duplicate_articles_across_stories(self):
        items = [
            _make_item("A", "https://a.com/1", ["AAPL", "MSFT"]),
        ]
        stories = _fallback_grouping(items)
        all_urls = [a.url for s in stories for a in s.source_articles]
        assert len(all_urls) == len(set(all_urls))

    def test_empty_input(self):
        assert _fallback_grouping([]) == []


@pytest.mark.asyncio
async def test_neutralize_news_no_llm():
    items = [
        _make_item("A", "https://a.com/1", ["AAPL"]),
        _make_item("B", "https://b.com/2", ["MSFT"]),
    ]
    stories = await neutralize_news(items, llm_provider=None)
    assert len(stories) == 2
    assert all(s.ticker_sentiments == [] for s in stories)


@pytest.mark.asyncio
async def test_neutralize_news_empty():
    stories = await neutralize_news([], llm_provider=None)
    assert stories == []


@pytest.mark.asyncio
async def test_neutralize_news_deduplicates():
    items = [
        _make_item("Same story", "https://a.com/1", ["AAPL"]),
        _make_item("Same story again", "https://a.com/1", ["MSFT"]),
        _make_item("Different", "https://b.com/2", ["AAPL"]),
    ]
    stories = await neutralize_news(items, llm_provider=None)
    total_articles = sum(len(s.source_articles) for s in stories)
    assert total_articles == 2  # deduped from 3 to 2
