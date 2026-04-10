from __future__ import annotations

import logging

from briefing.schemas import NewsItem, NeutralizedStory, TickerSentiment

logger = logging.getLogger(__name__)


async def neutralize_news(
    news_items: list[NewsItem],
    llm_provider=None,
) -> list[NeutralizedStory]:
    """Cluster and neutralize news articles using LLM.

    Articles are deduplicated by URL, then clustered globally (not per-ticker)
    so that a story affecting multiple tickers appears once with all related
    tickers listed.  Per-ticker sentiment is extracted during the same
    neutralization call at zero additional LLM cost.

    If no LLM provider is available, returns raw articles grouped by dominant
    ticker (no neutralization, no sentiment).
    """
    if not news_items:
        return []

    # -- Step 0: Deduplicate by URL across all tickers -------------------------
    unique_articles = _deduplicate(news_items)
    if not unique_articles:
        return []

    # -- Fallback when no LLM is available -------------------------------------
    if llm_provider is None:
        return _fallback_grouping(unique_articles)

    # -- LLM-powered pipeline --------------------------------------------------
    from briefing.llm.prompts import build_cluster_prompt, build_neutralize_prompt

    stories: list[NeutralizedStory] = []

    try:
        # Step 1: Global clustering — one LLM call for ALL articles
        cluster_prompt = build_cluster_prompt(unique_articles)
        cluster_resp = await llm_provider.complete_json(
            system=(
                "You are a financial news analyst. Group the following articles "
                "by the story they cover. Articles about the same event or topic "
                "should be in the same cluster, even if they mention different tickers."
            ),
            user=cluster_prompt,
            schema={
                "type": "object",
                "properties": {
                    "clusters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "story": {"type": "string"},
                                "article_indices": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                },
                            },
                        },
                    },
                },
            },
        )

        clusters = cluster_resp.get("clusters", [])
        if not clusters:
            # LLM returned empty — treat everything as one cluster
            clusters = [
                {"story": "News roundup", "article_indices": list(range(len(unique_articles)))}
            ]

        # Step 2: Neutralize each cluster
        for cluster in clusters:
            indices = cluster.get("article_indices", [])
            cluster_articles = [
                unique_articles[i] for i in indices if i < len(unique_articles)
            ]
            if not cluster_articles:
                continue

            # Union of all tickers mentioned across articles in this cluster
            all_tickers = sorted({
                t for a in cluster_articles for t in a.related_tickers
            })

            neutralize_prompt = build_neutralize_prompt(
                cluster_articles, related_tickers=all_tickers or None,
            )

            # Build the output schema — include ticker_sentiments when tickers are known
            output_props: dict = {
                "headline": {"type": "string"},
                "factual_summary": {"type": "string"},
                "key_facts": {"type": "array", "items": {"type": "string"}},
                "bias_analysis": {"type": "string"},
                "sentiment_range": {"type": "object"},
            }
            if all_tickers:
                output_props["ticker_sentiments"] = {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "sentiment": {"type": "string"},
                            "score": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                    },
                }

            neutral_resp = await llm_provider.complete_json(
                system=(
                    "You are a neutral financial news analyst. Your job is to strip "
                    "editorial bias and present only verified facts. Identify where "
                    "sources disagree. Never editorialize. Use precise, neutral language."
                ),
                user=neutralize_prompt,
                schema={"type": "object", "properties": output_props},
            )

            # Parse ticker sentiments
            raw_sentiments = neutral_resp.get("ticker_sentiments", [])
            ticker_sentiments = [
                TickerSentiment(
                    ticker=ts.get("ticker", ""),
                    sentiment=ts.get("sentiment", "neutral"),
                    score=float(ts.get("score", 0.0)),
                    reason=ts.get("reason", ""),
                )
                for ts in raw_sentiments
                if ts.get("ticker")
            ]

            stories.append(NeutralizedStory(
                headline=neutral_resp.get("headline", cluster.get("story", "")),
                factual_summary=neutral_resp.get("factual_summary", ""),
                source_articles=cluster_articles,
                sentiment_range=neutral_resp.get("sentiment_range", {}),
                bias_analysis=neutral_resp.get("bias_analysis", ""),
                key_facts=neutral_resp.get("key_facts", []),
                related_tickers=all_tickers,
                ticker_sentiments=ticker_sentiments,
            ))

    except Exception as e:
        logger.error("News neutralization failed: %s", e)
        # Fallback for all articles
        return _fallback_grouping(unique_articles)

    return stories


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deduplicate(news_items: list[NewsItem]) -> list[NewsItem]:
    """Remove duplicate articles by URL, preserving ticker relationships."""
    url_map: dict[str, NewsItem] = {}
    for item in news_items:
        if item.url in url_map:
            # Merge tickers from the duplicate into the existing entry
            existing = url_map[item.url]
            merged_tickers = list(dict.fromkeys(
                existing.related_tickers + item.related_tickers
            ))
            url_map[item.url] = existing.model_copy(
                update={"related_tickers": merged_tickers}
            )
        else:
            url_map[item.url] = item
    return list(url_map.values())


def _fallback_grouping(articles: list[NewsItem]) -> list[NeutralizedStory]:
    """Group articles by dominant ticker when no LLM is available."""
    by_ticker: dict[str, list[NewsItem]] = {}
    for item in articles:
        for ticker in item.related_tickers:
            by_ticker.setdefault(ticker, []).append(item)

    stories: list[NeutralizedStory] = []
    seen_urls: set[str] = set()

    for ticker, items in by_ticker.items():
        # Avoid duplicating articles already assigned to another ticker
        fresh = [i for i in items if i.url not in seen_urls]
        if not fresh:
            continue
        for i in fresh:
            seen_urls.add(i.url)

        stories.append(NeutralizedStory(
            headline=f"News for {ticker}",
            factual_summary=f"{len(fresh)} articles found",
            source_articles=fresh,
            key_facts=[i.title for i in fresh[:5]],
            related_tickers=[ticker],
        ))

    # Collect macro/general articles not assigned to any ticker
    unassigned = [item for item in articles if item.url not in seen_urls]
    if unassigned:
        stories.append(NeutralizedStory(
            headline="Market & Economy",
            factual_summary=f"{len(unassigned)} macro/general articles",
            source_articles=unassigned,
            key_facts=[i.title for i in unassigned[:5]],
            related_tickers=[],
        ))

    return stories
