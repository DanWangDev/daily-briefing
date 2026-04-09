from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.config import ApiKeysConfig
from briefing.schemas import CollectorResult, TickerQuote

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
                errors=["ALPHA_VANTAGE_KEY not configured, skipping"],
            )

        quotes: list[TickerQuote] = []
        errors: list[str] = []

        async with httpx.AsyncClient(timeout=15) as client:
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
                except Exception as e:
                    logger.warning("Alpha Vantage failed for %s: %s", ticker, e)
                    errors.append(f"Failed for {ticker}: {e}")

        return CollectorResult(
            source="alpha_vantage",
            collected_at=datetime.now(timezone.utc),
            quotes=quotes,
            errors=errors,
        )
