from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from briefing.config import AppConfig
from briefing.database import init_db
from briefing.web.app import create_app


@pytest.fixture
def app():
    config = AppConfig()
    config.database.path = ":memory:"
    application = create_app(config)
    init_db(config)
    return application


@pytest.mark.asyncio
async def test_dashboard_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "Daily Briefing" in resp.text


@pytest.mark.asyncio
async def test_newsmap_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/newsmap")
    assert resp.status_code == 200
    assert "News Map" in resp.text


@pytest.mark.asyncio
async def test_portfolio_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/portfolio")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_settings_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/settings")
    assert resp.status_code == 200
    assert "Timezone" in resp.text


@pytest.mark.asyncio
async def test_briefings_returns_200(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/briefings")
    assert resp.status_code == 200
