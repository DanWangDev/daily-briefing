"""Entry point: python -m briefing"""
from __future__ import annotations

import logging

import uvicorn

from briefing.config import load_config
from briefing.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    config = load_config()
    init_db(config)

    # Hydrate config from persisted settings (DB is source of truth for keys)
    from briefing.database import get_session
    from briefing.settings_store import load_settings
    with get_session() as session:
        load_settings(session, config)

    # Import here to avoid circular imports with DB init
    from briefing.web.app import create_app

    app = create_app(config)

    from briefing.scheduler import start_scheduler
    start_scheduler(config)

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
