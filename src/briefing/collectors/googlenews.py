from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from briefing.collectors._rss_utils import parse_rss_items
from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.schemas import CollectorResult, NewsItem

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_MAX_ARTICLES_PER_TICKER = 5
_USER_AGENT = "Mozilla/5.0 (compatible; DailyBriefing/0.1)"


class GoogleNewsCollector(BaseCollector):
    """Collects financial news from Google News RSS feeds. Free, no API key."""

    def __init__(self) -> None:
        self._rate_limiter = RateLimiter(calls_per_period=1, period_seconds=1.0)

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
                    resp = await client.get(
                        _GOOGLE_NEWS_RSS,
                        params={
                            "q": f"{ticker} stock",
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
