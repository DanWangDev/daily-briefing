# Daily Briefing

Automated financial intelligence for personal portfolios. Collects market data, news, and SEC filings from 6+ sources, neutralizes editorial bias with AI, and delivers a unified daily briefing with an interactive news map.

## The Problem

Financial news is noisy, biased, and scattered. The same earnings report gets spun as "bullish momentum" by one outlet and "slowing growth" by another. Tracking how geopolitical events, rate decisions, and macro trends affect your specific holdings requires checking multiple sources daily.

## What This Does

- **Collects** market data, news, and SEC filings from 6 sources continuously (every 2 hours for free sources)
- **Neutralizes** editorial bias using LLMs — strips spin, extracts only verified facts, notes where sources disagree
- **Scores** per-ticker sentiment on a -1.0 to +1.0 scale with reasoning
- **Visualizes** how news connects to your holdings via an interactive force-directed graph (News Map)
- **Delivers** a polished daily briefing to the web dashboard or your inbox

## Quick Start

```bash
# Install
pip install -e .

# Run
python -m briefing
# Open http://localhost:8000
```

1. Go to **Portfolio** — add your tickers (e.g., AAPL, MSFT, VOO)
2. Go to **Settings** — configure an LLM provider (or skip for raw news mode)
3. Click **Generate Now** on the dashboard

### Docker

```bash
docker-compose up --build
# Open http://localhost:8000
```

## Features

### News Collection (6 Sources)

| Source | Free | Key Required | What It Provides |
|--------|------|-------------|------------------|
| Yahoo Finance | Yes | No | Market quotes + news articles |
| Google News RSS | Yes | No | News per ticker |
| Financial RSS (CNBC, MarketWatch, Reuters) | Yes | No | General financial + macro news |
| SEC EDGAR | Yes | No | 10-K, 10-Q, 8-K filings |
| NewsAPI | 100 req/day free | Yes | Additional news coverage |
| Alpha Vantage | 25 req/day free | Yes | Supplementary quotes + news sentiment |

**Works with zero API keys.** The three free sources provide solid coverage out of the box. Add NewsAPI and Alpha Vantage keys in Settings for broader coverage.

### Background Collection

Free sources are polled every 2 hours automatically. Articles are cached in the database with URL-based dedup. When you generate a briefing, it pulls from the cache (instant) rather than live-fetching (5-10 seconds).

### AI-Powered News Neutralization

When an LLM is configured, each briefing run:

1. **Clusters** all articles by story (same event groups together, even across tickers)
2. **Neutralizes** each cluster — strips editorializing, extracts facts cited by 2+ sources
3. **Scores sentiment** per ticker (-1.0 to +1.0) with a one-line reason
4. **Flags bias** — notes where sources disagree or use loaded language

Without an LLM, briefings still generate with raw article groupings (no neutralization or sentiment).

### News Map

Full-screen dark-mode interactive graph showing how news stories connect to your holdings:

- **Ticker nodes** (blue rectangles) — your portfolio holdings
- **Story nodes** (sentiment-colored rectangles) — neutralized news clusters connected to related tickers
- **MARKET node** (amber diamond) — hub for macro/geopolitical news (Fed, tariffs, inflation)
- **Edges** — colored by sentiment (green = positive, red = negative, gray = neutral)
- **Detail panel** — click any node for full story with facts, sources, and per-ticker impact
- Zoom controls, keyboard shortcuts (Escape to close), responsive on mobile

### Macro/Geopolitical News

General market news (rate decisions, trade wars, inflation data) is captured even when it doesn't mention specific tickers. The RSS collector uses keyword matching for 30+ macro topics. These stories connect to the MARKET hub node on the news map.

### LLM Providers (4 Supported)

| Provider | Key Required | Notes |
|----------|-------------|-------|
| Anthropic (Claude) | Yes | Default. Recommended: `claude-haiku-4-5-20251001` |
| OpenAI (GPT) | Yes | Any GPT-4 or GPT-3.5 model |
| Alibaba Qwen | Yes | Via DashScope API (OpenAI-compatible) |
| Ollama | No | Local. Any installed model (llama3, mistral, etc.) |

Configure in Settings. Only one provider active at a time.

### Generation UX

"Generate Now" runs the pipeline in the background. The dashboard shows a progress card that polls every 2 seconds. If you navigate to another page, a toast notification tells you when the briefing is ready.

### Email Delivery

Optional. Configure SMTP in Settings to receive your briefing by email at the scheduled time.

## Configuration

All settings are managed through the web UI at `/settings`. They're encrypted and stored in the database (no `.env` files needed).

**Minimal `config.yaml`** (optional, only for database path):

```yaml
database:
  path: "./data/briefing.db"
```

Everything else — LLM keys, schedule, email — is configured in Settings and persisted in the DB.

### Schedule

- **Delivery time**: When the daily briefing auto-generates (default: 07:00)
- **Timezone**: Your local timezone (default: America/New_York)
- **Background collection**: Free sources polled every 2 hours (always on)

## Architecture

```
                    APScheduler
                    +-----------+
                    | every 2h  |-----> Free collectors -----> news_articles (cache)
                    | daily cron|-----> run_briefing() -----> briefings + sections
                    +-----------+
                         |
     FastAPI (port 8000) |
     +-------------------+-------------------+
     |                   |                   |
  Dashboard          News Map            Portfolio
  (HTMX)           (Cytoscape.js)       (HTMX)
     |
  Generate Now ---> asyncio.create_task()
                        |
                    Pipeline:
                    1. Read article cache (24h)
                    2. Live-fetch market quotes
                    3. Run paid collectors (if keys set)
                    4. Merge cached + fresh articles
                    5. LLM cluster + neutralize
                    6. Render HTML + graph data
                    7. Store briefing
```

**Stack**: Python 3.12+ / FastAPI / SQLAlchemy / SQLite / APScheduler / HTMX / Pico CSS / Cytoscape.js / Chart.js

## Project Structure

```
src/briefing/
  __main__.py              # Entry point
  config.py                # Pydantic config models
  database.py              # SQLAlchemy engine + sessions
  models.py                # ORM models (6 tables)
  schemas.py               # Pydantic schemas (NewsItem, TickerQuote, etc.)
  scheduler.py             # APScheduler (daily briefing + 2h collection)
  settings_store.py        # Encrypted settings persistence

  collectors/              # 6 data source collectors
    base.py                # BaseCollector interface + RateLimiter
    yahoo.py               # Yahoo Finance (quotes + news)
    googlenews.py           # Google News RSS
    rss.py                 # CNBC, MarketWatch, Reuters + macro filter
    newsapi.py             # NewsAPI (key required)
    alphavantage.py        # Alpha Vantage (key required)
    edgar.py               # SEC EDGAR filings

  llm/                     # LLM providers
    base.py                # BaseLLMProvider interface + factory
    anthropic_provider.py  # Claude
    openai_provider.py     # GPT
    qwen_provider.py       # Qwen (DashScope)
    ollama_provider.py     # Local Ollama
    prompts.py             # Clustering + neutralization prompts

  pipeline/                # Briefing generation
    orchestrator.py        # Main pipeline (run_briefing)
    news.py                # Dedup, cluster, neutralize
    market.py              # Market data aggregation
    filings.py             # Filing summarization
    article_store.py       # Article cache (store/retrieve/link)

  delivery/                # Output
    renderer.py            # HTML + Chart.js + newsmap graph data
    email.py               # SMTP delivery

  web/                     # Web UI
    app.py                 # FastAPI app factory
    routes/                # Route handlers
    templates/             # Jinja2 templates
    static/                # CSS
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Run the app with auto-reload (dev mode)
python -m uvicorn briefing.web.app:create_app --factory --reload --app-dir src --port 8000
```

Note: dev mode (`--reload`) skips DB init and scheduler. Use `python -m briefing` for full functionality.

## Requirements

- Python 3.12+
- No external services required (SQLite, no Redis/Celery)
- Optional: LLM API key for news neutralization
- Optional: NewsAPI / Alpha Vantage keys for additional coverage
- Optional: SMTP server for email delivery
- Optional: Docker for containerized deployment

## License

Private project.
