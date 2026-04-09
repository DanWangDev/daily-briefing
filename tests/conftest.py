from __future__ import annotations

import pytest

from briefing.config import AppConfig


@pytest.fixture
def config():
    return AppConfig()
