from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone

from briefing.collectors.alphavantage import AlphaVantageCollector
from briefing.collectors.edgar import EdgarCollector
from briefing.collectors.googlenews import GoogleNewsCollector
from briefing.collectors.newsapi import NewsAPICollector
from briefing.collectors.rss import FinancialRSSCollector
from briefing.collectors.yahoo import YahooFinanceCollector
from briefing.config import AppConfig
from briefing.database import get_session
from briefing.delivery.renderer import render_briefing_html
from briefing.models import Briefing, BriefingSection, Holding
from briefing.pipeline.filings import summarize_filings
from briefing.pipeline.market import aggregate_market_data
from briefing.pipeline.news import neutralize_news
from briefing.schemas import CollectorResult

logger = logging.getLogger(__name__)


async def run_briefing(config: AppConfig) -> int:
    """Run the full briefing pipeline. Returns the briefing ID."""
    session = get_session()
    try:
        holdings = session.query(Holding).all()
        if not holdings:
            raise ValueError("No holdings in portfolio. Add tickers first.")

        tickers = [h.ticker for h in holdings]
        holdings_data = [
            {"ticker": h.ticker, "name": h.name, "shares": h.shares, "cost_basis": h.cost_basis}
            for h in holdings
        ]

        # Create briefing record
        briefing = Briefing(
            market_date=date.today(),
            status="pending",
            portfolio_snapshot=json.dumps(holdings_data),
        )
        session.add(briefing)
        session.commit()
        briefing_id = briefing.id

    finally:
        session.close()

    try:
        # Step 0: Pull cached articles from background collection
        from briefing.pipeline.article_store import get_recent_articles, link_to_briefing
        cached_news = get_recent_articles(tickers, hours=24)
        logger.info("Article cache: %d articles from last 24h", len(cached_news))

        # Step 1: Collect from all sources concurrently (market data + paid news)
        logger.info("Collecting data for %d tickers: %s", len(tickers), tickers)
        results = await _collect_all(config, tickers, holdings_data)

        # Step 2: Aggregate market data
        market_data = aggregate_market_data(results)

        # Step 3: Get LLM provider (if configured)
        llm_provider = _get_llm_provider(config)

        # Step 4: Gather news and filings — merge cached + freshly collected
        all_news = list(cached_news)
        all_filings = []
        for r in results:
            all_news.extend(r.news)
            all_filings.extend(r.filings)
        logger.info("Total news for processing: %d (%d cached + %d fresh)",
                     len(all_news), len(cached_news), len(all_news) - len(cached_news))

        # Step 5: Process news and filings (can run in parallel)
        neutralized_stories, filing_summaries = await asyncio.gather(
            neutralize_news(all_news, llm_provider, locale=config.language),
            summarize_filings(all_filings, llm_provider, locale=config.language),
        )

        # Step 6: Render and store sections
        _store_sections(
            briefing_id=briefing_id,
            market_data=market_data,
            holdings_data=holdings_data,
            neutralized_stories=neutralized_stories,
            filing_summaries=filing_summaries,
        )

        # Step 7: Render full HTML
        html = render_briefing_html(
            market_data=market_data,
            holdings_data=holdings_data,
            neutralized_stories=neutralized_stories,
            filing_summaries=filing_summaries,
            lang=config.language,
        )

        # Step 8: Update briefing status
        session = get_session()
        try:
            briefing = session.query(Briefing).filter(Briefing.id == briefing_id).first()
            briefing.summary_html = html
            briefing.status = "completed"
            session.commit()
        finally:
            session.close()

        # Step 9: Link cached articles to this briefing
        article_urls = [a.url for a in all_news if a.url]
        link_to_briefing(briefing_id, article_urls)

        logger.info("Briefing #%d completed successfully", briefing_id)
        return briefing_id

    except Exception as e:
        logger.error("Briefing pipeline failed: %s", e)
        session = get_session()
        try:
            briefing = session.query(Briefing).filter(Briefing.id == briefing_id).first()
            if briefing:
                briefing.status = "failed"
                session.commit()
        finally:
            session.close()
        raise


async def _collect_all(
    config: AppConfig,
    tickers: list[str],
    holdings_data: list[dict] | None = None,
) -> list[CollectorResult]:
    """Run all collectors concurrently."""
    ticker_names = {h["ticker"]: h.get("name", "") for h in (holdings_data or [])}
    collectors = [
        YahooFinanceCollector(),
        AlphaVantageCollector(config.api_keys),
        NewsAPICollector(config.api_keys),
        GoogleNewsCollector(),
        FinancialRSSCollector(ticker_names=ticker_names),
        EdgarCollector(),
    ]

    tasks = [c.collect(tickers) for c in collectors]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = []
    for collector, result in zip(collectors, results):
        if isinstance(result, Exception):
            logger.error("%s collector failed: %s", collector.name(), result)
            valid_results.append(CollectorResult(
                source=collector.name().lower().replace(" ", "_"),
                collected_at=datetime.now(timezone.utc),
                errors=[str(result)],
            ))
        else:
            if result.errors:
                for err in result.errors:
                    logger.warning("%s: %s", collector.name(), err)
            valid_results.append(result)

    return valid_results


def _get_llm_provider(config: AppConfig):
    """Create LLM provider from config. Returns None if not configured."""
    try:
        from briefing.llm.base import create_llm_provider
        return create_llm_provider(config.llm)
    except Exception as e:
        logger.warning("LLM provider unavailable: %s. Proceeding without neutralization.", e)
        return None


def _store_sections(
    briefing_id: int,
    market_data: dict,
    holdings_data: list[dict],
    neutralized_stories: list,
    filing_summaries: list[dict],
) -> None:
    """Store briefing sections in the database."""
    session = get_session()
    try:
        # Market overview section
        for ticker, quote in market_data.items():
            session.add(BriefingSection(
                briefing_id=briefing_id,
                section_type="market_data",
                ticker=ticker,
                content_json=quote.model_dump_json(),
            ))

        # News sections
        for story in neutralized_stories:
            session.add(BriefingSection(
                briefing_id=briefing_id,
                section_type="news",
                ticker=story.related_tickers[0] if story.related_tickers else None,
                content_json=story.model_dump_json(),
            ))

        # Filing sections
        for filing in filing_summaries:
            session.add(BriefingSection(
                briefing_id=briefing_id,
                section_type="filing",
                ticker=filing.get("ticker"),
                content_json=json.dumps(filing),
            ))

        session.commit()
    finally:
        session.close()
