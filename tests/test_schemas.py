from __future__ import annotations

from datetime import datetime

from briefing.schemas import (
    CollectorResult,
    HoldingCreate,
    NewsItem,
    NeutralizedStory,
    TickerQuote,
    TickerSentiment,
)


def test_ticker_quote_creation():
    q = TickerQuote(
        ticker="AAPL",
        price=150.0,
        change=2.5,
        change_pct=1.69,
        volume=50_000_000,
        day_high=152.0,
        day_low=148.0,
        source="yahoo",
    )
    assert q.ticker == "AAPL"
    assert q.price == 150.0
    assert q.market_cap is None


def test_ticker_sentiment():
    ts = TickerSentiment(
        ticker="NVDA",
        sentiment="negative",
        score=-0.7,
        reason="Tariff exposure",
    )
    assert ts.sentiment == "negative"
    assert ts.score == -0.7


def test_ticker_sentiment_defaults():
    ts = TickerSentiment(ticker="AAPL")
    assert ts.sentiment == "neutral"
    assert ts.score == 0.0
    assert ts.reason == ""


def test_neutralized_story_with_sentiments():
    story = NeutralizedStory(
        headline="Test headline",
        factual_summary="Test summary",
        source_articles=[],
        related_tickers=["AAPL", "MSFT"],
        ticker_sentiments=[
            TickerSentiment(ticker="AAPL", sentiment="positive", score=0.8, reason="Good news"),
            TickerSentiment(ticker="MSFT", sentiment="negative", score=-0.3, reason="Bad news"),
        ],
    )
    assert len(story.ticker_sentiments) == 2
    assert story.ticker_sentiments[0].ticker == "AAPL"
    assert story.ticker_sentiments[1].sentiment == "negative"


def test_neutralized_story_defaults():
    story = NeutralizedStory(
        headline="H",
        factual_summary="S",
        source_articles=[],
    )
    assert story.ticker_sentiments == []
    assert story.related_tickers == []
    assert story.key_facts == []


def test_news_item():
    item = NewsItem(
        title="Test",
        source="Reuters",
        url="https://example.com",
        published_at=datetime(2026, 1, 1),
        snippet="Snippet",
        related_tickers=["AAPL"],
    )
    assert item.related_tickers == ["AAPL"]


def test_collector_result_defaults():
    result = CollectorResult(
        source="test",
        collected_at=datetime(2026, 1, 1),
    )
    assert result.quotes == []
    assert result.news == []
    assert result.filings == []
    assert result.errors == []


def test_holding_create():
    h = HoldingCreate(ticker="AAPL", shares=10.0, cost_basis=150.0)
    assert h.ticker == "AAPL"
