from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx

from briefing.collectors.base import BaseCollector, RateLimiter
from briefing.schemas import CollectorResult, SECFiling

logger = logging.getLogger(__name__)

EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions"
USER_AGENT = "DailyBriefing/1.0 (admin@daily-briefing.local)"


class EdgarCollector(BaseCollector):
    """Collects SEC filings from EDGAR (10 req/sec, very generous)."""

    def __init__(self) -> None:
        self._rate_limiter = RateLimiter(calls_per_period=5, period_seconds=1.0)
        self._cik_cache: dict[str, str] = {}

    def name(self) -> str:
        return "SEC EDGAR"

    async def collect(self, tickers: list[str]) -> CollectorResult:
        filings: list[SECFiling] = []
        errors: list[str] = []

        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for ticker in tickers:
                try:
                    await self._rate_limiter.acquire()
                    cik = await self._resolve_cik(client, ticker)
                    if not cik:
                        errors.append(f"Could not resolve CIK for {ticker}")
                        continue

                    await self._rate_limiter.acquire()
                    ticker_filings = await self._get_recent_filings(client, cik, ticker)
                    filings.extend(ticker_filings)
                except Exception as e:
                    logger.warning("EDGAR failed for %s: %s", ticker, e)
                    errors.append(f"Failed for {ticker}: {e}")

        return CollectorResult(
            source="sec_edgar",
            collected_at=datetime.now(timezone.utc),
            filings=filings,
            errors=errors,
        )

    async def _resolve_cik(self, client: httpx.AsyncClient, ticker: str) -> str | None:
        """Resolve ticker to CIK number."""
        if ticker in self._cik_cache:
            return self._cik_cache[ticker]

        resp = await client.get(
            "https://www.sec.gov/cgi-bin/browse-edgar",
            params={
                "action": "getcompany",
                "company": ticker,
                "CIK": ticker,
                "type": "",
                "dateb": "",
                "owner": "include",
                "count": "1",
                "search_text": "",
                "output": "atom",
            },
        )

        # Try the ticker-to-CIK mapping file instead
        try:
            resp2 = await client.get("https://www.sec.gov/files/company_tickers.json")
            data = resp2.json()
            for entry in data.values():
                if entry.get("ticker", "").upper() == ticker.upper():
                    cik = str(entry["cik_str"]).zfill(10)
                    self._cik_cache[ticker] = cik
                    return cik
        except Exception:
            pass

        return None

    async def _get_recent_filings(
        self,
        client: httpx.AsyncClient,
        cik: str,
        ticker: str,
    ) -> list[SECFiling]:
        """Get recent filings for a CIK."""
        resp = await client.get(f"{EDGAR_SUBMISSIONS}/CIK{cik}.json")
        if resp.status_code != 200:
            return []

        data = resp.json()
        company_name = data.get("name", ticker)
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        descriptions = recent.get("primaryDocDescription", [])

        target_forms = {"10-K", "10-Q", "8-K", "S-1", "DEF 14A"}
        results = []

        for i, form_type in enumerate(forms[:50]):
            if form_type not in target_forms:
                continue

            filed_str = dates[i] if i < len(dates) else ""
            try:
                filed_date = date.fromisoformat(filed_str)
            except ValueError:
                continue

            # Only include filings from the last 30 days
            if (date.today() - filed_date).days > 30:
                continue

            acc = accessions[i].replace("-", "") if i < len(accessions) else ""
            desc = descriptions[i] if i < len(descriptions) else form_type
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}"

            results.append(SECFiling(
                ticker=ticker,
                company_name=company_name,
                form_type=form_type,
                filed_date=filed_date,
                description=desc or form_type,
                url=url,
            ))

        return results
