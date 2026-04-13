from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


# --- Market Data ---

class TickerQuote(BaseModel):
    ticker: str
    price: float
    change: float
    change_pct: float
    volume: int
    market_cap: float | None = None
    pe_ratio: float | None = None
    day_high: float
    day_low: float
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    source: str


# --- News ---

class TickerSentiment(BaseModel):
    """Per-ticker sentiment for a specific news story."""
    ticker: str
    sentiment: str = "neutral"  # "positive" | "negative" | "neutral"
    score: float = 0.0          # -1.0 to 1.0
    reason: str = ""


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: datetime
    snippet: str
    related_tickers: list[str] = []
    # Upstream-provided per-ticker sentiment hints (currently only Massive
    # populates this via its insights[] field). Used by the LLM prompt as a
    # reference signal — the LLM still produces its own final ticker_sentiments.
    prior_sentiments: list[TickerSentiment] = []


class NeutralizedStory(BaseModel):
    """Output of the news neutralization pipeline for a single story cluster."""
    headline: str
    factual_summary: str
    source_articles: list[NewsItem]
    sentiment_range: dict = {}
    bias_analysis: str = ""
    key_facts: list[str] = []
    related_tickers: list[str] = []
    ticker_sentiments: list[TickerSentiment] = []


# --- SEC Filings ---

class SECFiling(BaseModel):
    ticker: str
    company_name: str
    form_type: str
    filed_date: date
    description: str
    url: str


# --- Collector Result (unified output) ---

class CollectorResult(BaseModel):
    source: str
    collected_at: datetime
    quotes: list[TickerQuote] = []
    news: list[NewsItem] = []
    filings: list[SECFiling] = []
    errors: list[str] = []


# --- Portfolio ---

class HoldingCreate(BaseModel):
    ticker: str
    shares: float
    cost_basis: float


class HoldingUpdate(BaseModel):
    shares: float | None = None
    cost_basis: float | None = None


class HoldingResponse(BaseModel):
    id: int
    ticker: str
    name: str
    shares: float
    cost_basis: float
    current_price: float | None = None
    total_value: float | None = None
    gain_loss: float | None = None
    gain_loss_pct: float | None = None


# --- Briefing ---

class BriefingSummary(BaseModel):
    id: int
    generated_at: datetime
    market_date: date
    status: str


class BriefingDetail(BaseModel):
    id: int
    generated_at: datetime
    market_date: date
    status: str
    portfolio_snapshot: dict = {}
    sections: list[BriefingSectionData] = []


class BriefingSectionData(BaseModel):
    section_type: str
    ticker: str | None = None
    content: dict = {}


# Fix forward reference
BriefingDetail.model_rebuild()
