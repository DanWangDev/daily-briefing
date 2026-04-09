from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import yfinance as yf

from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.schemas import CollectorResult, TickerQuote

logger = logging.getLogger(__name__)


class YahooFinanceCollector(BaseCollector):
    """Collects market data from Yahoo Finance using yfinance."""

    def __init__(self) -> None:
        self._rate_limiter = RateLimiter(calls_per_period=5, period_seconds=5.0)

    def name(self) -> str:
        return "Yahoo Finance"

    async def collect(self, tickers: list[str]) -> CollectorResult:
        """Fetch quotes for all tickers. Uses yfinance batch download."""
        errors: list[str] = []
        quotes: list[TickerQuote] = []

        try:
            await self._rate_limiter.acquire()
            # yfinance is synchronous, run in executor
            data = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_batch, tickers
            )
            for ticker_str, quote in data.items():
                if quote is not None:
                    quotes.append(quote)
                else:
                    errors.append(f"No data returned for {ticker_str}")
        except Exception as e:
            logger.error("Yahoo Finance batch fetch failed: %s", e)
            errors.append(f"Batch fetch failed: {e}")

        return CollectorResult(
            source="yahoo_finance",
            collected_at=datetime.now(timezone.utc),
            quotes=quotes,
            errors=errors,
        )

    def _fetch_batch(self, tickers: list[str]) -> dict[str, TickerQuote | None]:
        """Synchronous batch fetch using yfinance."""
        results: dict[str, TickerQuote | None] = {}

        for ticker_str in tickers:
            try:
                ticker = yf.Ticker(ticker_str)
                info = ticker.info

                if not info or "currentPrice" not in info and "regularMarketPrice" not in info:
                    results[ticker_str] = None
                    continue

                price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose", 0)
                change = price - prev_close if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0

                results[ticker_str] = TickerQuote(
                    ticker=ticker_str,
                    price=price,
                    change=round(change, 2),
                    change_pct=round(change_pct, 2),
                    volume=info.get("volume") or info.get("regularMarketVolume", 0),
                    market_cap=info.get("marketCap"),
                    pe_ratio=info.get("trailingPE"),
                    day_high=info.get("dayHigh") or info.get("regularMarketDayHigh", 0),
                    day_low=info.get("dayLow") or info.get("regularMarketDayLow", 0),
                    fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
                    fifty_two_week_low=info.get("fiftyTwoWeekLow"),
                    source="yahoo_finance",
                )
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", ticker_str, e)
                results[ticker_str] = None

        return results
