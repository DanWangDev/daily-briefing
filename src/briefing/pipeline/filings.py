from __future__ import annotations

import logging

from briefing.schemas import SECFiling

logger = logging.getLogger(__name__)


async def summarize_filings(
    filings: list[SECFiling],
    llm_provider=None,
    locale: str = "en",
) -> list[dict]:
    """Summarize SEC filings using LLM. Falls back to raw filing data if no LLM."""
    if not filings:
        return []

    lang_suffix = " Respond in Chinese (\u7b80\u4f53\u4e2d\u6587)." if locale != "en" else ""

    summaries = []
    for filing in filings:
        base = {
            "ticker": filing.ticker,
            "company_name": filing.company_name,
            "form_type": filing.form_type,
            "filed_date": filing.filed_date.isoformat(),
            "url": filing.url,
        }

        if llm_provider:
            try:
                resp = await llm_provider.complete(
                    system="You are a financial analyst. Briefly summarize the significance of this SEC filing in 1-2 sentences." + lang_suffix,
                    user=(
                        f"Company: {filing.company_name} ({filing.ticker})\n"
                        f"Filing: {filing.form_type} filed on {filing.filed_date}\n"
                        f"Description: {filing.description}"
                    ),
                    max_tokens=200,
                )
                base["summary"] = resp.content
            except Exception as e:
                logger.warning("Filing summary failed for %s: %s", filing.ticker, e)
                base["summary"] = filing.description
        else:
            base["summary"] = filing.description

        summaries.append(base)

    return summaries
