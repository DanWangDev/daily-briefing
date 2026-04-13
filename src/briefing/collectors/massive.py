"""Massive.com news collector (formerly Polygon.io).

Fetches the last 24h of global financial news from the /v2/reference/news
endpoint in a single paginated walk, filters client-side to portfolio tickers,
and passes through the per-ticker `insights[]` sentiment as prior_sentiments
hints for the LLM neutralization stage.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.config import ApiKeysConfig
from briefing.schemas import CollectorResult, NewsItem, TickerSentiment

logger = logging.getLogger(__name__)

MASSIVE_NEWS_URL = "https://api.massive.com/v2/reference/news"
MAX_ARTICLES = 200          # hard cap per run to bound cost / memory
MAX_PAGES = 5               # defensive cap on pagination walks
LOOKBACK_HOURS = 24
SANITY_MAX_AGE_HOURS = 48   # bail if the page's oldest article is older than this

# Massive sentiment labels → numeric scores. Massive doesn't provide a numeric
# score; the LLM stage can refine these if it disagrees.
_SENTIMENT_SCORE = {
    "positive": 0.5,
    "negative": -0.5,
    "neutral": 0.0,
}


class MassiveCollector(BaseCollector):
    """Collects ticker-tagged news from Massive.com (free tier: 5 calls/min)."""

    def __init__(self, api_keys: ApiKeysConfig) -> None:
        self._api_key = api_keys.massive
        # Free tier: 5 calls/min. The built-in limiter prevents 429s on
        # bursty runs even though a normal briefing run makes only 1-5 calls.
        self._rate_limiter = RateLimiter(calls_per_period=5, period_seconds=60)

    def name(self) -> str:
        return "Massive"

    async def collect(self, tickers: list[str]) -> CollectorResult:
        if not self._api_key:
            return CollectorResult(
                source="massive",
                collected_at=datetime.now(timezone.utc),
                errors=["Massive key not configured — set it in Settings"],
            )

        portfolio = {t.upper() for t in tickers if t}
        if not portfolio:
            return CollectorResult(
                source="massive",
                collected_at=datetime.now(timezone.utc),
            )

        since = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
        sanity_cutoff = datetime.now(timezone.utc) - timedelta(hours=SANITY_MAX_AGE_HOURS)

        all_news: list[NewsItem] = []
        errors: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                url: str | None = MASSIVE_NEWS_URL
                params: dict | None = {
                    "published_utc.gte": since.isoformat(),
                    "order": "desc",
                    "sort": "published_utc",
                    "limit": 100,
                    "apiKey": self._api_key,
                }

                for page in range(MAX_PAGES):
                    if url is None:
                        break
                    await self._rate_limiter.acquire()

                    resp = await client.get(url, params=params)
                    if resp.status_code != 200:
                        errors.append(
                            f"Massive HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                        break

                    data = resp.json()
                    results = data.get("results") or []
                    if not results:
                        break

                    kept_this_page = 0
                    for article in results:
                        item = self._build_news_item(article, portfolio)
                        if item is None:
                            continue
                        all_news.append(item)
                        kept_this_page += 1
                        if len(all_news) >= MAX_ARTICLES:
                            break

                    if len(all_news) >= MAX_ARTICLES:
                        break

                    # Sanity bail: if the oldest article on this page is older
                    # than our cutoff, further pages are useless.
                    oldest_iso = results[-1].get("published_utc")
                    if oldest_iso:
                        try:
                            oldest = datetime.fromisoformat(
                                oldest_iso.replace("Z", "+00:00")
                            )
                            if oldest < sanity_cutoff:
                                break
                        except ValueError:
                            pass

                    # Follow cursor. Massive's next_url omits apiKey, so we
                    # must re-inject it each time or the next call 401s.
                    next_url = data.get("next_url")
                    if not next_url:
                        break
                    url = next_url
                    params = {"apiKey": self._api_key}

        except Exception as e:  # noqa: BLE001
            logger.warning("Massive collector failed: %s", e)
            errors.append(f"Massive fetch failed: {e}")

        return CollectorResult(
            source="massive",
            collected_at=datetime.now(timezone.utc),
            news=all_news,
            errors=errors,
        )

    def _build_news_item(
        self, article: dict, portfolio: set[str]
    ) -> NewsItem | None:
        """Map a Massive article dict → NewsItem, or None if no portfolio overlap."""
        article_tickers = {
            str(t).upper() for t in (article.get("tickers") or []) if t
        }
        matched = article_tickers & portfolio
        if not matched:
            return None

        published_iso = article.get("published_utc", "")
        try:
            published_at = datetime.fromisoformat(
                published_iso.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            published_at = datetime.now(timezone.utc)

        publisher = article.get("publisher") or {}
        source_name = publisher.get("name") or "Massive"

        prior: list[TickerSentiment] = []
        for insight in article.get("insights") or []:
            t = str(insight.get("ticker") or "").upper()
            if t not in portfolio:
                continue
            sentiment = (insight.get("sentiment") or "neutral").lower()
            if sentiment not in _SENTIMENT_SCORE:
                sentiment = "neutral"
            prior.append(TickerSentiment(
                ticker=t,
                sentiment=sentiment,
                score=_SENTIMENT_SCORE[sentiment],
                reason=insight.get("sentiment_reasoning") or "",
            ))

        return NewsItem(
            title=article.get("title") or "Untitled",
            source=source_name,
            url=article.get("article_url") or "",
            published_at=published_at,
            snippet=article.get("description") or "",
            related_tickers=sorted(matched),
            prior_sentiments=prior,
        )
