from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from briefing.collectors._rss_utils import parse_rss_items
from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.schemas import CollectorResult, NewsItem

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_MAX_ARTICLES_PER_TICKER = 15
_USER_AGENT = "Mozilla/5.0 (compatible; DailyBriefing/0.1)"


class GoogleNewsCollector(BaseCollector):
    """Collects financial news from Google News RSS feeds. Free, no API key."""

    def __init__(self, ticker_names: dict[str, str] | None = None) -> None:
        self._rate_limiter = RateLimiter(calls_per_period=1, period_seconds=1.0)
        self._ticker_names = ticker_names or {}

    def name(self) -> str:
        return "Google News"

    async def collect(self, tickers: list[str]) -> CollectorResult:
        all_news: list[NewsItem] = []
        errors: list[str] = []

        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            for ticker in tickers:
                try:
                    await self._rate_limiter.acquire()
                    # Include company name in search for small-cap tickers
                    query = f"{ticker} stock"
                    name = self._ticker_names.get(ticker, "")
                    if name:
                        query = f"{ticker} {name} stock"
                    resp = await client.get(
                        _GOOGLE_NEWS_RSS,
                        params={
                            "q": query,
                            "hl": "en-US",
                            "gl": "US",
                            "ceid": "US:en",
                        },
                    )
                    if resp.status_code != 200:
                        errors.append(
                            f"Google News returned {resp.status_code} for {ticker}"
                        )
                        continue

                    items = parse_rss_items(resp.content)
                    for item in items[:_MAX_ARTICLES_PER_TICKER]:
                        source = item["source"]
                        title = item["title"]

                        # Google News appends " - SourceName" to titles
                        if not source and " - " in title:
                            title, source = title.rsplit(" - ", 1)

                        all_news.append(NewsItem(
                            title=title.strip(),
                            source=source.strip() or "Google News",
                            url=item["link"],
                            published_at=item["pub_date"],
                            snippet=item["description"][:500] if item["description"] else "",
                            related_tickers=[ticker],
                        ))

                except Exception as e:
                    logger.warning("Google News failed for %s: %s", ticker, e)
                    errors.append(f"Failed for {ticker}: {e}")

        return CollectorResult(
            source="google_news",
            collected_at=datetime.now(timezone.utc),
            news=all_news,
            errors=errors,
        )
