from __future__ import annotations

from datetime import datetime, timezone

from briefing.schemas import NewsItem


def _today_header() -> str:
    """Current-date anchor so the LLM doesn't hallucinate a stale year."""
    return f"Reference: today is {datetime.now(timezone.utc).strftime('%Y-%m-%d')} UTC.\n\n"


def _fmt_published(article: NewsItem) -> str:
    if article.published_at is None:
        return "unknown"
    pub = article.published_at
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    return pub.strftime("%Y-%m-%d %H:%M UTC")


def build_cluster_prompt(articles: list[NewsItem], locale: str = "en") -> str:
    """Build a prompt for clustering articles by story."""
    lines = []
    for i, article in enumerate(articles):
        lines.append(f"[{i}] ({_fmt_published(article)}) {article.source}: {article.title}")
        if article.snippet:
            lines.append(f"    {article.snippet[:200]}")
        lines.append("")

    lang_instruction = ""
    if locale != "en":
        lang_instruction = (
            "\nIMPORTANT: Return ALL text (story labels) in Chinese (\u7b80\u4f53\u4e2d\u6587). "
            "Keep ticker symbols in English.\n"
        )

    return (
        _today_header()
        + "Group the following news articles by the story they cover. "
        "Articles about the same event or topic should be in the same cluster. "
        "Return JSON with a 'clusters' array. Each cluster has a 'story' (short label) "
        "and 'article_indices' (array of integer indices).\n\n"
        + lang_instruction
        + "Articles:\n" + "\n".join(lines)
    )


def build_neutralize_prompt(
    articles: list[NewsItem],
    related_tickers: list[str] | None = None,
    locale: str = "en",
) -> str:
    """Build a prompt for neutralizing a cluster of articles.

    When *related_tickers* is provided the LLM also produces per-ticker
    sentiment scores used by the News Map visualization.
    """
    lines = []
    for article in articles:
        lines.append(f"Source: {article.source}")
        lines.append(f"Published: {_fmt_published(article)}")
        lines.append(f"Title: {article.title}")
        lines.append(f"Content: {article.snippet[:500]}")
        if article.prior_sentiments:
            lines.append("Prior sentiment hints (from upstream source, use as reference — you are free to refine or override):")
            for ps in article.prior_sentiments:
                reason = (ps.reason or "").strip()
                if len(reason) > 240:
                    reason = reason[:240] + "..."
                lines.append(f"  - {ps.ticker}: {ps.sentiment}{' — ' + reason if reason else ''}")
        lines.append("")

    ticker_block = ""
    if related_tickers:
        ticker_list = ", ".join(related_tickers)
        ticker_block = (
            f"\nThe following portfolio tickers are related to this story: {ticker_list}\n"
            "For EACH ticker, assess how this news impacts it specifically.\n"
            "Return a ticker_sentiments array with objects containing:\n"
            '  - ticker: the ticker symbol\n'
            '  - sentiment: "positive", "negative", or "neutral"\n'
            '  - score: float from -1.0 (very negative) to 1.0 (very positive)\n'
            '  - reason: one-sentence explanation of the impact on this specific ticker\n\n'
        )

    return (
        _today_header()
        + "Analyze these articles covering the same story. Produce a neutral summary.\n\n"
        "Rules:\n"
        "- Extract ONLY facts reported by 2+ sources, or clearly attribute single-source claims\n"
        "- Remove editorializing words (soaring, plummeting, devastating, stunning)\n"
        "- Note where sources disagree on facts or interpretation\n"
        "- Separate 'what happened' from 'what commentators think it means'\n"
        "- Use the Published dates above as the source of truth for when events occurred; do NOT infer a year from memory\n\n"
        + ticker_block
        + "Return JSON with:\n"
        "- headline: neutral, factual headline\n"
        "- factual_summary: 2-3 paragraph neutral summary\n"
        "- key_facts: array of undisputed bullet points\n"
        "- bias_analysis: how coverage differed between sources\n"
        "- sentiment_range: {most_bullish: source_name, most_bearish: source_name}\n"
        + ("- ticker_sentiments: array of per-ticker sentiment objects (see above)\n" if related_tickers else "")
        + (_locale_instruction(locale))
        + "\nArticles:\n" + "\n".join(lines)
    )


def _locale_instruction(locale: str) -> str:
    if locale == "en":
        return ""
    return (
        "\nIMPORTANT: Write ALL output text in Chinese (\u7b80\u4f53\u4e2d\u6587). "
        "This includes the headline, factual_summary, key_facts, bias_analysis, "
        "and ticker sentiment reasons. Keep ticker symbols and proper nouns in English.\n"
    )
