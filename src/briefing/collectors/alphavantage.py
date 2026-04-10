from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.config import ApiKeysConfig
from briefing.schemas import CollectorResult, NewsItem, TickerQuote

logger = logging.getLogger(__name__)

AV_BASE = "https://www.alphavantage.co/query"


class AlphaVantageCollector(BaseCollector):
    """Supplementary market data from Alpha Vantage (25 req/day free tier)."""

    def __init__(self, api_keys: ApiKeysConfig) -> None:
        self._api_key = api_keys.alpha_vantage
        # 25 requests per day = very conservative
        self._rate_limiter = RateLimiter(calls_per_period=25, period_seconds=86400)

    def name(self) -> str:
        return "Alpha Vantage"

    async def collect(self, tickers: list[str]) -> CollectorResult:
        if not self._api_key:
            return CollectorResult(
                source="alpha_vantage",
                collected_at=datetime.now(timezone.utc),
                errors=["Alpha Vantage key not configured — set it in Settings"],
            )

        quotes: list[TickerQuote] = []
        news: list[NewsItem] = []
        errors: list[str] = []
        rate_limited = False
        quotes_fetched = 0

        async with httpx.AsyncClient(timeout=15) as client:
            # Phase 1: Fetch quotes (priority)
            for ticker in tickers:
                try:
                    await self._rate_limiter.acquire()
                    resp = await client.get(AV_BASE, params={
                        "function": "GLOBAL_QUOTE",
                        "symbol": ticker,
                        "apikey": self._api_key,
                    })
                    data = resp.json()

                    if "Note" in data or "Information" in data:
                        errors.append(f"Alpha Vantage rate limited for {ticker}")
                        rate_limited = True
                        break

                    gq = data.get("Global Quote", {})
                    if not gq:
                        errors.append(f"No Alpha Vantage data for {ticker}")
                        continue

                    price = float(gq.get("05. price", 0))
                    change = float(gq.get("09. change", 0))
                    change_pct = float(gq.get("10. change percent", "0").rstrip("%"))

                    quotes.append(TickerQuote(
                        ticker=ticker,
                        price=price,
                        change=round(change, 2),
                        change_pct=round(change_pct, 2),
                        volume=int(gq.get("06. volume", 0)),
                        day_high=float(gq.get("03. high", 0)),
                        day_low=float(gq.get("04. low", 0)),
                        source="alpha_vantage",
                    ))
                    quotes_fetched += 1
                except Exception as e:
                    logger.warning("Alpha Vantage failed for %s: %s", ticker, e)
                    errors.append(f"Failed for {ticker}: {e}")

            # Phase 2: Fetch news if budget allows (25 req/day total)
            if not rate_limited and quotes_fetched + len(tickers) <= 20:
                for ticker in tickers:
                    try:
                        await self._rate_limiter.acquire()
                        resp = await client.get(AV_BASE, params={
                            "function": "NEWS_SENTIMENT",
                            "tickers": ticker,
                            "apikey": self._api_key,
                        })
                        data = resp.json()

                        if "Note" in data or "Information" in data:
                            errors.append("Alpha Vantage rate limited during news fetch")
                            break

                        for article in data.get("feed", [])[:5]:
                            pub_str = article.get("time_published", "")
                            try:
                                pub_date = datetime.strptime(pub_str, "%Y%m%dT%H%M%S")
                                pub_date = pub_date.replace(tzinfo=timezone.utc)
                            except (ValueError, TypeError):
                                pub_date = datetime.now(timezone.utc)

                            news.append(NewsItem(
                                title=article.get("title", ""),
                                source=article.get("source", "Alpha Vantage"),
                                url=article.get("url", ""),
                                published_at=pub_date,
                                snippet=article.get("summary", ""),
                                related_tickers=[ticker],
                            ))
                    except Exception as e:
                        logger.warning("Alpha Vantage news failed for %s: %s", ticker, e)
                        errors.append(f"News failed for {ticker}: {e}")
            elif not rate_limited:
                logger.info(
                    "Skipping Alpha Vantage news: budget tight (%d quotes, %d tickers)",
                    quotes_fetched, len(tickers),
                )

        return CollectorResult(
            source="alpha_vantage",
            collected_at=datetime.now(timezone.utc),
            quotes=quotes,
            news=news,
            errors=errors,
        )
