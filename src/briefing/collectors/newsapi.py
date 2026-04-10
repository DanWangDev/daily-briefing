from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.config import ApiKeysConfig
from briefing.schemas import CollectorResult, NewsItem

logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2/everything"


class NewsAPICollector(BaseCollector):
    """Collects financial news from NewsAPI (100 req/day free tier)."""

    def __init__(self, api_keys: ApiKeysConfig) -> None:
        self._api_key = api_keys.newsapi
        self._rate_limiter = RateLimiter(calls_per_period=100, period_seconds=86400)

    def name(self) -> str:
        return "NewsAPI"

    async def collect(self, tickers: list[str]) -> CollectorResult:
        if not self._api_key:
            return CollectorResult(
                source="newsapi",
                collected_at=datetime.now(timezone.utc),
                errors=["NewsAPI key not configured — set it in Settings"],
            )

        all_news: list[NewsItem] = []
        errors: list[str] = []

        async with httpx.AsyncClient(timeout=15) as client:
            for ticker in tickers:
                try:
                    await self._rate_limiter.acquire()
                    resp = await client.get(NEWSAPI_BASE, params={
                        "q": f'"{ticker}" stock',
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": 10,
                        "apiKey": self._api_key,
                    })
                    data = resp.json()

                    if data.get("status") != "ok":
                        msg = data.get("message", "Unknown error")
                        errors.append(f"NewsAPI error for {ticker}: {msg}")
                        continue

                    for article in data.get("articles", []):
                        published = article.get("publishedAt", "")
                        try:
                            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            pub_dt = datetime.now(timezone.utc)

                        all_news.append(NewsItem(
                            title=article.get("title") or "Untitled",
                            source=article.get("source", {}).get("name", "Unknown"),
                            url=article.get("url") or "",
                            published_at=pub_dt,
                            snippet=article.get("description") or article.get("content") or "",
                            related_tickers=[ticker],
                        ))
                except Exception as e:
                    logger.warning("NewsAPI failed for %s: %s", ticker, e)
                    errors.append(f"Failed for {ticker}: {e}")

        return CollectorResult(
            source="newsapi",
            collected_at=datetime.now(timezone.utc),
            news=all_news,
            errors=errors,
        )
