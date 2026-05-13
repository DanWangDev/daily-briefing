from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from briefing.schemas import NewsItem, NeutralizedStory, TickerSentiment

logger = logging.getLogger(__name__)

# Articles older than this are dropped before neutralization. Some collectors
# (RSS, Google News, Yahoo) return arbitrarily old hits when their search
# matches a stale headline, and the upstream cache filters by collected_at,
# not published_at — so a 2-year-old article can land in today's briefing.
_MAX_ARTICLE_AGE_HOURS = 48


async def neutralize_news(
    news_items: list[NewsItem],
    llm_provider=None,
    locale: str = "en",
) -> list[NeutralizedStory]:
    """Cluster and neutralize news articles using LLM.

    Articles are deduplicated by URL, then split into two pools:

    - **ticker articles** (those with at least one entry in
      ``related_tickers``) go through the normal clustering + per-cluster
      neutralization path. Per-ticker sentiment is extracted during the
      neutralize call.

    - **macro articles** (empty ``related_tickers`` — typically from the
      RSS collector's macro catch-all) are bundled into a single dedicated
      "Market & Macro" story. They skip the clustering LLM call entirely,
      which prevents them from being absorbed into ticker clusters and
      losing their macro identity (which would make them disappear from
      the news-map MARKET hub).

    If no LLM provider is available, returns raw articles grouped by
    dominant ticker via the fallback path.
    """
    if not news_items:
        return []

    deduped = _deduplicate(news_items)
    unique_articles = _filter_recent(deduped)
    dropped = len(deduped) - len(unique_articles)
    if dropped:
        logger.info(
            "Filtered %d stale articles (older than %dh)",
            dropped,
            _MAX_ARTICLE_AGE_HOURS,
        )
    if not unique_articles:
        return []

    if llm_provider is None:
        return _fallback_grouping(unique_articles)

    ticker_articles = [a for a in unique_articles if a.related_tickers]
    macro_articles = [a for a in unique_articles if not a.related_tickers]
    logger.info(
        "Neutralization input: %d ticker articles, %d macro articles",
        len(ticker_articles),
        len(macro_articles),
    )

    lang_suffix = (
        " Respond entirely in Chinese (\u7b80\u4f53\u4e2d\u6587)."
        if locale != "en"
        else ""
    )
    stories: list[NeutralizedStory] = []

    if ticker_articles:
        try:
            logger.info("Starting LLM clustering for %d ticker articles", len(ticker_articles))
            ticker_stories = await _neutralize_ticker_articles(
                ticker_articles, llm_provider, locale, lang_suffix
            )
            logger.info("LLM clustering produced %d stories from %d articles",
                        len(ticker_stories), len(ticker_articles))
            stories.extend(ticker_stories)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ticker news neutralization failed (falling back to per-ticker grouping): %s", exc)
            stories.extend(_fallback_grouping(ticker_articles))

    if macro_articles:
        try:
            macro_story = await _neutralize_macro_bundle(
                macro_articles, llm_provider, locale, lang_suffix
            )
            if macro_story is not None:
                stories.append(macro_story)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Macro neutralization failed, using bare fallback: %s", exc
            )
            stories.append(_macro_fallback_story(macro_articles, locale))

    return stories


# ---------------------------------------------------------------------------
# LLM pipeline: ticker-tagged articles (clustering + neutralize)
# ---------------------------------------------------------------------------

async def _neutralize_ticker_articles(
    articles: list[NewsItem],
    llm_provider,
    locale: str,
    lang_suffix: str,
) -> list[NeutralizedStory]:
    """Existing clustering + neutralization path, scoped to ticker articles."""
    from briefing.llm.prompts import build_cluster_prompt, build_neutralize_prompt

    cluster_prompt = build_cluster_prompt(articles, locale=locale)
    cluster_resp = await llm_provider.complete_json(
        system=(
            "You are a financial news analyst. Group the following articles "
            "by the story they cover. Articles about the same event or topic "
            "should be in the same cluster, even if they mention different tickers."
            + lang_suffix
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
        logger.warning("LLM clustering returned 0 clusters for %d articles — using single fallback cluster", len(articles))
        clusters = [
            {
                "story": "News roundup",
                "article_indices": list(range(len(articles))),
            }
        ]

    stories: list[NeutralizedStory] = []
    for cluster in clusters:
        indices = cluster.get("article_indices", [])
        cluster_articles = [articles[i] for i in indices if i < len(articles)]
        if not cluster_articles:
            continue

        all_tickers = sorted({
            t for a in cluster_articles for t in a.related_tickers
        })

        neutralize_prompt = build_neutralize_prompt(
            cluster_articles,
            related_tickers=all_tickers or None,
            locale=locale,
        )

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
                + lang_suffix
            ),
            user=neutralize_prompt,
            schema={"type": "object", "properties": output_props},
        )

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

        stories.append(
            NeutralizedStory(
                headline=neutral_resp.get("headline", cluster.get("story", "")),
                factual_summary=neutral_resp.get("factual_summary", ""),
                source_articles=cluster_articles,
                sentiment_range=neutral_resp.get("sentiment_range", {}),
                bias_analysis=neutral_resp.get("bias_analysis", ""),
                key_facts=neutral_resp.get("key_facts", []),
                related_tickers=all_tickers,
                ticker_sentiments=ticker_sentiments,
            )
        )

    return stories


# ---------------------------------------------------------------------------
# LLM pipeline: macro articles (single bundled neutralize)
# ---------------------------------------------------------------------------

async def _neutralize_macro_bundle(
    articles: list[NewsItem],
    llm_provider,
    locale: str,
    lang_suffix: str,
) -> NeutralizedStory | None:
    """Bundle macro articles into a single neutralized story with no tickers.

    Bypasses the LLM clustering stage entirely so macro content is
    guaranteed to land on the news-map MARKET hub instead of being
    absorbed into ticker clusters.
    """
    from briefing.llm.prompts import build_neutralize_prompt

    neutralize_prompt = build_neutralize_prompt(
        articles, related_tickers=None, locale=locale
    )
    neutral_resp = await llm_provider.complete_json(
        system=(
            "You are a neutral financial news analyst. Summarize these "
            "macro and market-wide news articles into a single briefing story "
            "about general market conditions (Fed, inflation, geopolitics, "
            "market commentary, etc.). Do NOT tag any specific tickers. "
            "Use precise, neutral language."
            + lang_suffix
        ),
        user=neutralize_prompt,
        schema={
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "factual_summary": {"type": "string"},
                "key_facts": {"type": "array", "items": {"type": "string"}},
                "bias_analysis": {"type": "string"},
            },
        },
    )

    default_headline = (
        "Market & Macro News" if locale == "en" else "\u5e02\u573a\u4e0e\u5b8f\u89c2\u65b0\u95fb"
    )
    return NeutralizedStory(
        headline=neutral_resp.get("headline") or default_headline,
        factual_summary=neutral_resp.get("factual_summary", ""),
        source_articles=articles,
        sentiment_range={},
        bias_analysis=neutral_resp.get("bias_analysis", ""),
        key_facts=neutral_resp.get("key_facts", []),
        related_tickers=[],
        ticker_sentiments=[],
    )


def _macro_fallback_story(
    articles: list[NewsItem], locale: str
) -> NeutralizedStory:
    """Bare macro story used when the LLM neutralize call fails."""
    headline = (
        "Market & Macro News" if locale == "en" else "\u5e02\u573a\u4e0e\u5b8f\u89c2\u65b0\u95fb"
    )
    return NeutralizedStory(
        headline=headline,
        factual_summary=f"{len(articles)} macro/general articles",
        source_articles=articles,
        key_facts=[a.title for a in articles[:5]],
        related_tickers=[],
        ticker_sentiments=[],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_recent(items: list[NewsItem]) -> list[NewsItem]:
    """Drop articles whose ``published_at`` is older than ``_MAX_ARTICLE_AGE_HOURS``.

    The cache layer (``article_store.get_recent_articles``) and the
    upstream collectors filter by ``collected_at`` (when *we* fetched
    the article), not ``published_at`` (when the publisher actually
    emitted it). RSS feeds, Google News, and Yahoo will happily return
    weeks- or years-old articles when their search hits a stale
    headline, and those would otherwise sail through dedup, get
    ticker-tagged via regex, and land in today's briefing. This guard
    is the single chokepoint that keeps stale content out.

    Articles with ``published_at = None`` are also dropped — without a
    timestamp we can't trust their freshness.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_MAX_ARTICLE_AGE_HOURS)
    fresh: list[NewsItem] = []
    for item in items:
        pub = item.published_at
        if pub is None:
            continue
        # Defensive: cache hits from the SQLite store can come back tz-naive.
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if pub >= cutoff:
            fresh.append(item)
    return fresh


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
            key_facts=[i.title for i in fresh[:15]],
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
