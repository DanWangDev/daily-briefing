from __future__ import annotations

import json
from datetime import date

from briefing.schemas import NeutralizedStory, TickerQuote


def _tts_button(label: str = "Read aloud") -> str:
    """Small speaker icon button for text-to-speech."""
    return (
        f'<button class="tts-btn" type="button" aria-label="{label}" '
        f'title="{label}">\U0001f509</button>'
    )


def render_briefing_html(
    market_data: dict[str, TickerQuote],
    holdings_data: list[dict],
    neutralized_stories: list[NeutralizedStory],
    filing_summaries: list[dict],
    lang: str = "en",
) -> str:
    """Render a complete briefing as HTML.

    Used by both web dashboard and email delivery.
    The HTML is fully readable without JavaScript (progressive enhancement).
    Chart.js data is embedded in script[type=application/json] blocks
    that the dashboard JS picks up for interactive visualization.
    """
    from briefing.web.i18n import get_translator
    _ = get_translator(lang)
    tts_label = _("tts.play")

    parts: list[str] = []

    # -- Compute portfolio metrics -------------------------------------------
    holdings_enriched: list[dict] = []
    total_value = 0.0
    total_cost = 0.0
    total_day_change = 0.0

    for h in holdings_data:
        ticker = h["ticker"]
        quote = market_data.get(ticker)
        if not quote:
            continue

        value = quote.price * h["shares"]
        cost = h["cost_basis"] * h["shares"]
        gain = value - cost
        gain_pct = (gain / cost * 100) if cost else 0
        day_change = quote.change * h["shares"]

        total_value += value
        total_cost += cost
        total_day_change += day_change

        holdings_enriched.append({
            "ticker": ticker,
            "name": h.get("name", ""),
            "shares": h["shares"],
            "cost_basis": h["cost_basis"],
            "price": quote.price,
            "change": quote.change,
            "change_pct": quote.change_pct,
            "day_high": quote.day_high,
            "day_low": quote.day_low,
            "value": value,
            "cost": cost,
            "gain": gain,
            "gain_pct": gain_pct,
            "day_change": day_change,
        })

    total_gain = total_value - total_cost
    total_gain_pct = (total_gain / total_cost * 100) if total_cost else 0
    day_change_pct = (total_day_change / (total_value - total_day_change) * 100) if (total_value - total_day_change) else 0

    # -- Chart data payload (JSON for Chart.js) ------------------------------
    chart_data = {
        "allocation": {
            "labels": [h["ticker"] for h in holdings_enriched],
            "values": [round(h["value"], 2) for h in holdings_enriched],
        },
        "dayChanges": {
            "labels": [h["ticker"] for h in holdings_enriched],
            "values": [round(h["change_pct"], 2) for h in holdings_enriched],
        },
        "totals": {
            "totalValue": round(total_value, 2),
            "totalGain": round(total_gain, 2),
            "totalGainPct": round(total_gain_pct, 2),
            "dayChange": round(total_day_change, 2),
            "dayChangePct": round(day_change_pct, 2),
        },
    }

    parts.append(
        f'<script type="application/json" id="briefing-chart-data">'
        f"{json.dumps(chart_data)}</script>"
    )

    # ========================================================================
    # SECTION 1: Portfolio Summary Hero
    # ========================================================================
    gain_class = "positive" if total_gain >= 0 else "negative"
    day_class = "positive" if total_day_change >= 0 else "negative"
    day_arrow = "\u25b2" if total_day_change >= 0 else "\u25bc"
    gain_arrow = "\u25b2" if total_gain >= 0 else "\u25bc"

    parts.append('<section class="briefing-section portfolio-hero">')
    date_fmt = date.today().strftime("%Y\u5e74%m\u6708%d\u65e5") if lang == "zh" else date.today().strftime("%B %d, %Y")
    parts.append(f'<h2>{_("renderer.portfolio_summary")} &mdash; {date_fmt} {_tts_button(tts_label)}</h2>')
    parts.append('<div class="hero-grid">')

    # Left: Key metrics
    parts.append('<div class="hero-metrics">')
    parts.append(f'<div class="metric-primary">')
    parts.append(f'<span class="metric-label">{_("renderer.total_value")}</span>')
    parts.append(f'<span class="metric-value">${total_value:,.2f}</span>')
    parts.append(f'</div>')
    parts.append(f'<div class="metric-row">')
    parts.append(f'<div class="metric-card {day_class}">')
    parts.append(f'<span class="metric-label">{_("renderer.today")}</span>')
    parts.append(f'<span class="metric-value">{day_arrow} ${abs(total_day_change):,.2f}</span>')
    parts.append(f'<span class="metric-detail">({day_change_pct:+.2f}%)</span>')
    parts.append(f'</div>')
    parts.append(f'<div class="metric-card {gain_class}">')
    parts.append(f'<span class="metric-label">{_("renderer.total_pl")}</span>')
    parts.append(f'<span class="metric-value">{gain_arrow} ${abs(total_gain):,.2f}</span>')
    parts.append(f'<span class="metric-detail">({total_gain_pct:+.2f}%)</span>')
    parts.append(f'</div>')
    parts.append(f'</div>')
    parts.append('</div>')  # hero-metrics

    # Right: Allocation donut chart canvas (Chart.js will draw here)
    parts.append('<div class="hero-chart">')
    parts.append('<canvas id="allocation-chart" width="260" height="260"></canvas>')
    # Fallback table for email / no-JS
    parts.append('<noscript><table class="allocation-fallback">')
    parts.append('<thead><tr><th>Ticker</th><th>Value</th><th>Weight</th></tr></thead><tbody>')
    for h in holdings_enriched:
        weight = (h["value"] / total_value * 100) if total_value else 0
        parts.append(
            f'<tr><td>{h["ticker"]}</td>'
            f'<td>${h["value"]:,.2f}</td>'
            f'<td>{weight:.1f}%</td></tr>'
        )
    parts.append('</tbody></table></noscript>')
    parts.append('</div>')  # hero-chart

    parts.append('</div>')  # hero-grid
    parts.append('</section>')

    # ========================================================================
    # SECTION 2: Holdings Cards
    # ========================================================================
    parts.append('<section class="briefing-section">')
    parts.append(f'<h2>{_("renderer.holdings")} {_tts_button(tts_label)}</h2>')
    parts.append('<div class="holdings-grid">')

    for h in holdings_enriched:
        change_class = "positive" if h["change"] >= 0 else "negative"
        gain_class = "positive" if h["gain"] >= 0 else "negative"
        change_arrow = "\u25b2" if h["change"] >= 0 else "\u25bc"
        gain_arrow_h = "\u25b2" if h["gain"] >= 0 else "\u25bc"
        weight = (h["value"] / total_value * 100) if total_value else 0

        # Day range bar position (where price sits between low and high)
        day_range = h["day_high"] - h["day_low"]
        if day_range > 0:
            range_pct = ((h["price"] - h["day_low"]) / day_range) * 100
        else:
            range_pct = 50

        parts.append(f'<div class="holding-card" data-ticker="{h["ticker"]}">')
        parts.append(f'<div class="holding-header">')
        parts.append(f'<span class="holding-ticker">{h["ticker"]}</span>')
        parts.append(f'<span class="holding-name">{_escape(h["name"])}</span>')
        parts.append(f'<span class="holding-weight">{weight:.1f}%</span>')
        parts.append(f'</div>')

        parts.append(f'<div class="holding-price">${h["price"]:,.2f}</div>')
        parts.append(f'<div class="holding-change {change_class}">')
        parts.append(f'{change_arrow} {h["change"]:+.2f} ({h["change_pct"]:+.2f}%)')
        parts.append(f'</div>')

        # Day range indicator
        parts.append(f'<div class="day-range">')
        parts.append(f'<span class="range-label">${h["day_low"]:,.2f}</span>')
        parts.append(f'<div class="range-bar">')
        parts.append(f'<div class="range-fill" style="width:{range_pct:.0f}%"></div>')
        parts.append(f'</div>')
        parts.append(f'<span class="range-label">${h["day_high"]:,.2f}</span>')
        parts.append(f'</div>')

        parts.append(f'<div class="holding-footer">')
        parts.append(f'<div class="holding-stat">')
        parts.append(f'<span class="stat-label">{h["shares"]:.2f} shares</span>')
        parts.append(f'<span class="stat-value">${h["value"]:,.2f}</span>')
        parts.append(f'</div>')
        parts.append(f'<div class="holding-stat {gain_class}">')
        parts.append(f'<span class="stat-label">{_("renderer.pl")}</span>')
        parts.append(f'<span class="stat-value">{gain_arrow_h} ${abs(h["gain"]):,.2f} ({h["gain_pct"]:+.2f}%)</span>')
        parts.append(f'</div>')
        parts.append(f'</div>')

        parts.append(f'</div>')  # holding-card

    parts.append('</div>')  # holdings-grid

    # Day performance bar chart
    parts.append('<div class="day-performance-chart">')
    parts.append('<canvas id="day-performance-chart" height="180"></canvas>')
    parts.append('</div>')

    parts.append('</section>')

    # ========================================================================
    # SECTION 3: News with Ticker Relationships
    # ========================================================================
    if neutralized_stories:
        # Build a mapping of ticker -> stories for the relationship data
        ticker_story_map: dict[str, list[int]] = {}
        for idx, story in enumerate(neutralized_stories):
            for t in story.related_tickers:
                if t not in ticker_story_map:
                    ticker_story_map[t] = []
                ticker_story_map[t].append(idx)

        news_link_data = {
            "stories": [
                {
                    "index": idx,
                    "headline": story.headline,
                    "tickers": story.related_tickers,
                }
                for idx, story in enumerate(neutralized_stories)
            ],
            "tickerMap": ticker_story_map,
        }

        parts.append(
            f'<script type="application/json" id="news-link-data">'
            f"{json.dumps(news_link_data)}</script>"
        )

        parts.append('<section class="briefing-section news-section">')
        parts.append(f'<h2>{_("renderer.news_analysis")} {_tts_button(tts_label)}</h2>')

        # Ticker filter pills
        all_news_tickers = sorted({t for s in neutralized_stories for t in s.related_tickers})
        if all_news_tickers:
            parts.append('<div class="news-filters">')
            parts.append('<button class="ticker-filter active" data-ticker="all">All</button>')
            for t in all_news_tickers:
                parts.append(f'<button class="ticker-filter" data-ticker="{t}">{t}</button>')
            parts.append('</div>')

        parts.append('<div class="news-list">')

        for idx, story in enumerate(neutralized_stories):
            tickers_data_attr = " ".join(story.related_tickers)

            parts.append(
                f'<article class="news-card" '
                f'data-story-index="{idx}" '
                f'data-tickers="{tickers_data_attr}">'
            )

            parts.append(f'<div class="news-card-header">')
            parts.append(f'<h3>{_escape(story.headline)}</h3>')
            # Ticker badges with links
            parts.append(f'<div class="ticker-badges">')
            for t in story.related_tickers:
                parts.append(
                    f'<a href="#" class="ticker-badge" '
                    f'data-ticker="{t}" '
                    f'title="Related to {t}">{t}</a>'
                )
            parts.append(f'</div>')
            parts.append(f'</div>')  # news-card-header

            parts.append(f'<p class="news-summary">{_escape(story.factual_summary)}</p>')

            if story.key_facts:
                parts.append('<ul class="news-facts">')
                for fact in story.key_facts:
                    parts.append(f"<li>{_escape(fact)}</li>")
                parts.append("</ul>")

            if story.bias_analysis:
                parts.append(
                    f'<div class="bias-analysis">'
                    f'<strong>Bias check:</strong> {_escape(story.bias_analysis)}'
                    f'</div>'
                )

            if story.source_articles:
                parts.append('<div class="news-sources">')
                source_links = []
                for article in story.source_articles[:5]:
                    source_links.append(
                        f'<a href="{_escape(article.url)}" target="_blank" '
                        f'rel="noopener">{_escape(article.source)}</a>'
                    )
                parts.append(f'Sources: {", ".join(source_links)}')
                parts.append('</div>')

            parts.append('</article>')  # news-card

        parts.append('</div>')  # news-list
        parts.append('</section>')

    # ========================================================================
    # SECTION 4: SEC Filings Timeline
    # ========================================================================
    if filing_summaries:
        parts.append('<section class="briefing-section filings-section">')
        parts.append(f'<h2>{_("renderer.sec_filings")} {_tts_button(tts_label)}</h2>')
        parts.append('<div class="filings-timeline">')

        for f in filing_summaries:
            parts.append(f'<div class="filing-item" data-ticker="{_escape(f["ticker"])}">')
            parts.append(f'<div class="filing-marker"></div>')
            parts.append(f'<div class="filing-content">')
            parts.append(f'<div class="filing-header">')
            parts.append(
                f'<span class="ticker-badge" data-ticker="{_escape(f["ticker"])}">'
                f'{_escape(f["ticker"])}</span>'
            )
            parts.append(
                f'<a href="{_escape(f["url"])}" target="_blank" '
                f'rel="noopener" class="filing-type">{_escape(f["form_type"])}</a>'
            )
            parts.append(f'<span class="filing-date">{f["filed_date"]}</span>')
            parts.append(f'</div>')
            if f.get("summary"):
                parts.append(f'<p class="filing-summary">{_escape(f["summary"])}</p>')
            parts.append(f'</div>')
            parts.append(f'</div>')

        parts.append('</div>')  # filings-timeline
        parts.append('</section>')

    # ========================================================================
    # News Map graph data (JSON for Cytoscape.js on /newsmap)
    # ========================================================================
    graph_data: dict = {"nodes": [], "edges": []}

    for h in holdings_enriched:
        graph_data["nodes"].append({
            "id": f"ticker-{h['ticker']}",
            "type": "ticker",
            "label": h["ticker"],
            "name": h.get("name", ""),
            "value": round(h["value"], 2),
            "change_pct": round(h["change_pct"], 2),
        })

    # Add virtual MARKET hub node if any story has no ticker connections
    has_macro = any(not s.related_tickers for s in neutralized_stories)
    if has_macro:
        graph_data["nodes"].append({
            "id": "ticker-MARKET",
            "type": "market",
            "label": "MARKET",
            "name": "Macro & Geopolitical",
            "value": 0,
            "change_pct": 0,
        })

    for idx, story in enumerate(neutralized_stories):
        story_id = f"story-{idx}"
        sentiments_by_ticker = {
            ts.ticker: ts for ts in getattr(story, "ticker_sentiments", [])
        }

        graph_data["nodes"].append({
            "id": story_id,
            "type": "story",
            "label": story.headline[:60] if story.headline else "",
            "headline": story.headline,
            "summary": story.factual_summary,
            "key_facts": story.key_facts,
            "sources": len(story.source_articles),
        })

        if story.related_tickers:
            for ticker in story.related_tickers:
                ts = sentiments_by_ticker.get(ticker)
                graph_data["edges"].append({
                    "source": story_id,
                    "target": f"ticker-{ticker}",
                    "sentiment": ts.sentiment if ts else "neutral",
                    "score": ts.score if ts else 0.0,
                    "reason": ts.reason if ts else "",
                })
        elif has_macro:
            # Connect macro/general stories to the MARKET hub
            graph_data["edges"].append({
                "source": story_id,
                "target": "ticker-MARKET",
                "sentiment": "neutral",
                "score": 0.0,
                "reason": "Broad market impact",
            })

    parts.append(
        f'<script type="application/json" id="newsmap-graph-data">'
        f"{json.dumps(graph_data)}</script>"
    )

    return "\n".join(parts)


def _escape(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
