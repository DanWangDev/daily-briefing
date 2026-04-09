from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from briefing.database import Base


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Briefing(Base):
    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    market_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary_html: Mapped[str] = mapped_column(Text, default="")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    portfolio_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending")


class BriefingSection(Base):
    __tablename__ = "briefing_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    briefing_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    section_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(10), nullable=True)
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    content_html: Mapped[str] = mapped_column(Text, default="")


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    briefing_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    original_summary: Mapped[str] = mapped_column(Text, default="")
    neutralized_summary: Mapped[str] = mapped_column(Text, default="")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    bias_flags: Mapped[str] = mapped_column(Text, default="[]")


class MarketDataCache(Base):
    __tablename__ = "market_data_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
