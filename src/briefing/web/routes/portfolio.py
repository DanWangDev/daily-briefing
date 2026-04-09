from __future__ import annotations

import asyncio
import logging

import yfinance as yf
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from briefing.database import get_session
from briefing.models import Holding
from briefing.schemas import HoldingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_holdings_with_prices() -> tuple[list[HoldingResponse], float, float]:
    """Load all holdings and enrich with current prices."""
    session = get_session()
    try:
        holdings = session.query(Holding).order_by(Holding.ticker).all()
        if not holdings:
            return [], 0.0, 0.0

        tickers = [h.ticker for h in holdings]
        prices = _fetch_current_prices(tickers)

        responses = []
        total_value = 0.0
        total_cost = 0.0

        for h in holdings:
            price = prices.get(h.ticker)
            value = price * h.shares if price else None
            cost = h.cost_basis * h.shares
            gain = value - cost if value else None
            gain_pct = (gain / cost * 100) if gain and cost else None

            if value:
                total_value += value
            total_cost += cost

            responses.append(HoldingResponse(
                id=h.id,
                ticker=h.ticker,
                name=h.name,
                shares=h.shares,
                cost_basis=h.cost_basis,
                current_price=price,
                total_value=value,
                gain_loss=gain,
                gain_loss_pct=gain_pct,
            ))

        total_gain = total_value - total_cost if total_value else None
        return responses, total_value, total_gain
    finally:
        session.close()


def _fetch_current_prices(tickers: list[str]) -> dict[str, float | None]:
    """Fetch current prices for tickers. Returns {ticker: price}."""
    prices: dict[str, float | None] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            prices[t] = info.get("currentPrice") or info.get("regularMarketPrice")
        except Exception:
            prices[t] = None
    return prices


def _resolve_ticker_name(ticker: str) -> str:
    """Get company name for a ticker."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker


@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio_page(request: Request):
    holdings, total_value, total_gain = await asyncio.get_event_loop().run_in_executor(
        None, _get_holdings_with_prices
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="portfolio.html",
        context={
            "holdings": holdings,
            "total_value": total_value,
            "total_gain_loss": total_gain,
        },
    )


@router.post("/api/portfolio", response_class=HTMLResponse)
async def add_holding(
    request: Request,
    ticker: str = Form(...),
    shares: float = Form(...),
    cost_basis: float = Form(...),
):
    ticker = ticker.upper().strip()

    session = get_session()
    try:
        existing = session.query(Holding).filter(Holding.ticker == ticker).first()
        if existing:
            existing.shares = existing.shares + shares
            existing.cost_basis = (existing.cost_basis + cost_basis) / 2
        else:
            name = await asyncio.get_event_loop().run_in_executor(
                None, _resolve_ticker_name, ticker
            )
            session.add(Holding(ticker=ticker, name=name, shares=shares, cost_basis=cost_basis))
        session.commit()
    finally:
        session.close()

    holdings, total_value, total_gain = await asyncio.get_event_loop().run_in_executor(
        None, _get_holdings_with_prices
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="partials/holdings_table.html",
        context={
            "holdings": holdings,
            "total_value": total_value,
            "total_gain_loss": total_gain,
        },
    )


@router.delete("/api/portfolio/{holding_id}", response_class=HTMLResponse)
async def delete_holding(request: Request, holding_id: int):
    session = get_session()
    try:
        holding = session.query(Holding).filter(Holding.id == holding_id).first()
        if holding:
            session.delete(holding)
            session.commit()
    finally:
        session.close()

    holdings, total_value, total_gain = await asyncio.get_event_loop().run_in_executor(
        None, _get_holdings_with_prices
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="partials/holdings_table.html",
        context={
            "holdings": holdings,
            "total_value": total_value,
            "total_gain_loss": total_gain,
        },
    )


@router.get("/api/portfolio")
async def list_holdings_json():
    holdings, total_value, total_gain = _get_holdings_with_prices()
    return {
        "holdings": [h.model_dump() for h in holdings],
        "total_value": total_value,
        "total_gain_loss": total_gain,
    }
