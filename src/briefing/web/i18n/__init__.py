"""Lightweight JSON-based i18n for the Daily Briefing web UI."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

I18N_DIR = Path(__file__).parent


@lru_cache(maxsize=4)
def load_translations(lang: str) -> dict[str, str]:
    """Load translation strings for *lang*, falling back to English for missing keys."""
    en_path = I18N_DIR / "en.json"
    en = json.loads(en_path.read_text("utf-8")) if en_path.exists() else {}

    if lang == "en":
        return en

    lang_path = I18N_DIR / f"{lang}.json"
    if not lang_path.exists():
        return en

    overlay = json.loads(lang_path.read_text("utf-8"))
    return {**en, **overlay}


def get_translator(lang: str):
    """Return a ``_()`` function that resolves translation keys.

    Supports ``{name}`` interpolation::

        _("badge.new_articles", count=5)
        # "5 new articles ready"
    """
    strings = load_translations(lang)

    def _(key: str, **kwargs) -> str:
        val = strings.get(key, key)
        if kwargs:
            for k, v in kwargs.items():
                val = val.replace(f"{{{k}}}", str(v))
        return val

    return _
