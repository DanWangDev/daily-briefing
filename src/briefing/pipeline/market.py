from __future__ import annotations

import logging

from briefing.schemas import CollectorResult, TickerQuote

logger = logging.getLogger(__name__)


def aggregate_market_data(results: list[CollectorResult]) -> dict[str, TickerQuote]:
    """Merge market data from multiple collectors. Yahoo is primary, others supplement."""
    by_ticker: dict[str, TickerQuote] = {}

    # Process in priority order: yahoo first, then others fill gaps
    priority = ["yahoo_finance", "alpha_vantage"]
    sorted_results = sorted(
        results,
        key=lambda r: priority.index(r.source) if r.source in priority else 99,
    )

    for result in sorted_results:
        for quote in result.quotes:
            if quote.ticker not in by_ticker:
                by_ticker[quote.ticker] = quote
            else:
                # Fill in missing fields from supplementary sources
                existing = by_ticker[quote.ticker]
                by_ticker[quote.ticker] = TickerQuote(
                    ticker=existing.ticker,
                    price=existing.price or quote.price,
                    change=existing.change if existing.change != 0 else quote.change,
                    change_pct=existing.change_pct if existing.change_pct != 0 else quote.change_pct,
                    volume=existing.volume or quote.volume,
                    market_cap=existing.market_cap or quote.market_cap,
                    pe_ratio=existing.pe_ratio or quote.pe_ratio,
                    day_high=existing.day_high or quote.day_high,
                    day_low=existing.day_low or quote.day_low,
                    fifty_two_week_high=existing.fifty_two_week_high or quote.fifty_two_week_high,
                    fifty_two_week_low=existing.fifty_two_week_low or quote.fifty_two_week_low,
                    source=existing.source,
                )

    return by_ticker
