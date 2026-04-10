from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


def _mask(key: str) -> str:
    """Return a masked version of a key for display."""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


class ScheduleConfig(BaseModel):
    timezone: str = "America/New_York"
    delivery_time: str = "07:00"
    email_enabled: bool = False


class LLMConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"
    base_url: str | None = None
    _api_keys: dict[str, str] = {}

    def set_api_key(self, provider: str, key: str) -> None:
        self._api_keys[provider] = key

    def get_api_key(self, provider: str | None = None) -> str | None:
        provider = provider or self.provider
        return self._api_keys.get(provider) or None

    @property
    def api_key(self) -> str | None:
        return self.get_api_key(self.provider)

    def api_key_display(self, provider: str) -> str:
        """Return masked key for display, or empty string."""
        return _mask(self.get_api_key(provider) or "")


class ApiKeysConfig(BaseModel):
    _keys: dict[str, str] = {}

    def set_key(self, name: str, key: str) -> None:
        self._keys[name] = key

    @property
    def alpha_vantage(self) -> str | None:
        return self._keys.get("alpha_vantage") or None

    @property
    def newsapi(self) -> str | None:
        return self._keys.get("newsapi") or None

    def key_display(self, name: str) -> str:
        return _mask(self._keys.get(name, ""))


class EmailConfig(BaseModel):
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    from_address: str = "briefing@example.com"
    to_address: str = "me@example.com"
    _credentials: dict[str, str] = {}

    def set_credential(self, name: str, value: str) -> None:
        self._credentials[name] = value

    @property
    def username(self) -> str | None:
        return self._credentials.get("username") or None

    @property
    def password(self) -> str | None:
        return self._credentials.get("password") or None


class DatabaseConfig(BaseModel):
    path: str = "./data/briefing.db"


class AppConfig(BaseModel):
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    api_keys: ApiKeysConfig = Field(default_factory=ApiKeysConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load config from YAML file.

    Only ``database.path`` is read from the YAML file — all other settings
    are persisted in the database and hydrated at startup via
    ``load_settings()``.  Falls back to defaults if no file is found.
    """
    candidates = [
        config_path,
        Path("config.yaml"),
        Path.home() / ".config" / "daily-briefing" / "config.yaml",
    ]

    for path in candidates:
        if path is None:
            continue
        path = Path(path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            db_section = data.get("database", {})
            return AppConfig(
                database=DatabaseConfig.model_validate(db_section),
            )

    return AppConfig()
