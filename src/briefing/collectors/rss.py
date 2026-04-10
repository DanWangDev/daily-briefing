from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from briefing.collectors._rss_utils import parse_rss_items
from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.schemas import CollectorResult, NewsItem

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; DailyBriefing/0.1)"

_FEEDS: list[tuple[str, str]] = [
    (
        "CNBC Finance",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml"
        "?partnerId=wrss01&id=100003114",
    ),
    (
        "CNBC Top News",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml"
        "?partnerId=wrss01&id=100727362",
    ),
    (
        "MarketWatch Top Stories",
        "http://feeds.marketwatch.com/marketwatch/topstories/",
    ),
    (
        "MarketWatch Market Pulse",
        "http://feeds.marketwatch.com/marketwatch/marketpulse/",
    ),
]


class FinancialRSSCollector(BaseCollector):
    """Collects news from general financial RSS feeds and filters by ticker.

    Fetches CNBC and MarketWatch RSS feeds, then matches articles against
    portfolio tickers and company names. Free, no API key required.
    """

    def __init__(self, ticker_names: dict[str, str] | None = None) -> None:
        self._rate_limiter = RateLimiter(calls_per_period=2, period_seconds=1.0)
        self._ticker_names = ticker_names or {}

    def name(self) -> str:
        return "Financial RSS"

    async def collect(self, tickers: list[str]) -> CollectorResult:
        patterns = _build_patterns(tickers, self._ticker_names)
        all_news: list[NewsItem] = []
        errors: list[str] = []

        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            for feed_name, feed_url in _FEEDS:
                try:
                    await self._rate_limiter.acquire()
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        errors.append(f"{feed_name} returned {resp.status_code}")
                        continue

                    items = parse_rss_items(resp.content)
                    for item in items:
                        matched = _match_tickers(
                            item["title"],
                            item["description"],
                            patterns,
                        )
                        if not matched:
                            continue

                        all_news.append(NewsItem(
                            title=item["title"],
                            source=item["source"] or feed_name,
                            url=item["link"],
                            published_at=item["pub_date"],
                            snippet=item["description"][:500] if item["description"] else "",
                            related_tickers=matched,
                        ))

                except Exception as e:
                    logger.warning("%s feed failed: %s", feed_name, e)
                    errors.append(f"{feed_name}: {e}")

        return CollectorResult(
            source="financial_rss",
            collected_at=datetime.now(timezone.utc),
            news=all_news,
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Ticker matching helpers
# ---------------------------------------------------------------------------

def _build_patterns(
    tickers: list[str],
    ticker_names: dict[str, str],
) -> dict[str, list[re.Pattern]]:
    """Build regex patterns for each ticker and its company name."""
    patterns: dict[str, list[re.Pattern]] = {}
    for ticker in tickers:
        ticker_patterns: list[re.Pattern] = []

        # Short tickers (1-2 chars) get strict matching to avoid false positives
        if len(ticker) <= 2:
            ticker_patterns.append(re.compile(rf"(?<!\w){re.escape(ticker)}(?!\w)"))
        else:
            ticker_patterns.append(
                re.compile(rf"\b{re.escape(ticker)}\b", re.IGNORECASE)
            )

        # Company name pattern (if available)
        name = ticker_names.get(ticker, "")
        if name:
            # Use first meaningful word of company name (skip "Inc.", "Corp.", etc.)
            core_name = _core_company_name(name)
            if core_name and len(core_name) > 2:
                ticker_patterns.append(
                    re.compile(rf"\b{re.escape(core_name)}\b", re.IGNORECASE)
                )

        patterns[ticker] = ticker_patterns

    return patterns


def _core_company_name(name: str) -> str:
    """Extract the core company name, stripping suffixes like Inc., Corp., etc."""
    suffixes = r",?\s*\b(Corporation|Company|Inc\.?|Corp\.?|Co\.?|Ltd\.?|LLC|LP|ETF|Class\s+\w)\s*\.?"
    cleaned = re.sub(suffixes, "", name, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"[,.\s]+$", "", cleaned).strip()
    return cleaned


def _match_tickers(
    title: str,
    description: str,
    patterns: dict[str, list[re.Pattern]],
) -> list[str]:
    """Return list of tickers that match the article title or description."""
    text = f"{title} {description}"
    matched: list[str] = []

    for ticker, ticker_patterns in patterns.items():
        for pattern in ticker_patterns:
            if pattern.search(text):
                matched.append(ticker)
                break

    return sorted(matched)
