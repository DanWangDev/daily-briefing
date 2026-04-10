from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


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
        # UI-set key takes priority over env var
        if provider in self._api_keys and self._api_keys[provider]:
            return self._api_keys[provider]
        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "qwen": "DASHSCOPE_API_KEY",
        }
        env_var = env_map.get(provider)
        if env_var:
            return os.environ.get(env_var)
        return None

    @property
    def api_key(self) -> str | None:
        return self.get_api_key(self.provider)

    def api_key_display(self, provider: str) -> str:
        """Return masked key for display, or empty string."""
        key = self.get_api_key(provider)
        if not key:
            return ""
        if len(key) <= 8:
            return "****"
        return key[:4] + "****" + key[-4:]


class ApiKeysConfig(BaseModel):
    alpha_vantage_env: str = "ALPHA_VANTAGE_KEY"
    newsapi_env: str = "NEWSAPI_KEY"
    _direct_keys: dict[str, str] = {}

    def set_key(self, name: str, key: str) -> None:
        self._direct_keys[name] = key

    def _get(self, name: str, env_var: str) -> str | None:
        if name in self._direct_keys and self._direct_keys[name]:
            return self._direct_keys[name]
        return os.environ.get(env_var)

    @property
    def alpha_vantage(self) -> str | None:
        return self._get("alpha_vantage", self.alpha_vantage_env)

    @property
    def newsapi(self) -> str | None:
        return self._get("newsapi", self.newsapi_env)

    def key_display(self, name: str) -> str:
        env_map = {"alpha_vantage": self.alpha_vantage_env, "newsapi": self.newsapi_env}
        key = self._get(name, env_map.get(name, ""))
        if not key:
            return ""
        if len(key) <= 8:
            return "****"
        return key[:4] + "****" + key[-4:]


class EmailConfig(BaseModel):
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    from_address: str = "briefing@example.com"
    to_address: str = "me@example.com"

    @property
    def username(self) -> str | None:
        return os.environ.get("EMAIL_USER")

    @property
    def password(self) -> str | None:
        return os.environ.get("EMAIL_PASS")


class DatabaseConfig(BaseModel):
    path: str = "./data/briefing.db"


class AppConfig(BaseModel):
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    api_keys: ApiKeysConfig = Field(default_factory=ApiKeysConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load config from YAML file. Falls back to defaults if file not found."""
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
            return AppConfig.model_validate(data)

    return AppConfig()
