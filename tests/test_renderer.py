from __future__ import annotations

import json
import re

from briefing.delivery.renderer import render_briefing_html, _escape
from briefing.schemas import NeutralizedStory, TickerQuote, TickerSentiment


def _make_market_data():
    return {
        "AAPL": TickerQuote(
            ticker="AAPL", price=150.0, change=1.5, change_pct=1.01,
            volume=1_000_000, day_high=152.0, day_low=148.0, source="test",
        ),
        "MSFT": TickerQuote(
            ticker="MSFT", price=300.0, change=-2.0, change_pct=-0.66,
            volume=500_000, day_high=303.0, day_low=298.0, source="test",
        ),
    }


def _make_holdings():
    return [
        {"ticker": "AAPL", "name": "Apple Inc.", "shares": 10, "cost_basis": 100.0},
        {"ticker": "MSFT", "name": "Microsoft Corp", "shares": 5, "cost_basis": 250.0},
    ]


class TestRenderer:
    def test_renders_html(self):
        html = render_briefing_html(_make_market_data(), _make_holdings(), [], [])
        assert "AAPL" in html
        assert "MSFT" in html
        assert "Portfolio Summary" in html

    def test_embeds_chart_data(self):
        html = render_briefing_html(_make_market_data(), _make_holdings(), [], [])
        match = re.search(r'id="briefing-chart-data">(.*?)</script>', html)
        assert match
        data = json.loads(match.group(1))
        assert "allocation" in data
        assert "dayChanges" in data
        assert len(data["allocation"]["labels"]) == 2

    def test_embeds_newsmap_graph_data(self):
        html = render_briefing_html(_make_market_data(), _make_holdings(), [], [])
        match = re.search(r'id="newsmap-graph-data">(.*?)</script>', html)
        assert match
        data = json.loads(match.group(1))
        assert len(data["nodes"]) == 2  # 2 ticker nodes, 0 stories
        assert data["edges"] == []

    def test_newsmap_graph_with_stories(self):
        stories = [
            NeutralizedStory(
                headline="Test story",
                factual_summary="Summary",
                source_articles=[],
                related_tickers=["AAPL", "MSFT"],
                ticker_sentiments=[
                    TickerSentiment(ticker="AAPL", sentiment="positive", score=0.8, reason="Good"),
                    TickerSentiment(ticker="MSFT", sentiment="negative", score=-0.5, reason="Bad"),
                ],
            ),
        ]
        html = render_briefing_html(_make_market_data(), _make_holdings(), stories, [])
        match = re.search(r'id="newsmap-graph-data">(.*?)</script>', html)
        data = json.loads(match.group(1))

        assert len(data["nodes"]) == 3  # 2 tickers + 1 story
        assert len(data["edges"]) == 2  # story -> AAPL, story -> MSFT

        # Check sentiment on edges
        sentiments = {e["target"]: e["sentiment"] for e in data["edges"]}
        assert sentiments["ticker-AAPL"] == "positive"
        assert sentiments["ticker-MSFT"] == "negative"

    def test_newsmap_graph_story_node_fields(self):
        stories = [
            NeutralizedStory(
                headline="A very long headline that should be truncated",
                factual_summary="The summary",
                source_articles=[],
                related_tickers=["AAPL"],
                key_facts=["Fact 1", "Fact 2"],
            ),
        ]
        html = render_briefing_html(_make_market_data(), _make_holdings(), stories, [])
        match = re.search(r'id="newsmap-graph-data">(.*?)</script>', html)
        data = json.loads(match.group(1))

        story_node = next(n for n in data["nodes"] if n["type"] == "story")
        assert len(story_node["label"]) <= 60
        assert story_node["headline"] == "A very long headline that should be truncated"
        assert story_node["summary"] == "The summary"
        assert story_node["key_facts"] == ["Fact 1", "Fact 2"]


class TestEscape:
    def test_escapes_html_entities(self):
        assert _escape('<script>alert("xss")</script>') == (
            "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;"
        )

    def test_escapes_ampersand(self):
        assert _escape("P&L") == "P&amp;L"
