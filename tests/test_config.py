from __future__ import annotations

from briefing.config import AppConfig, LLMConfig, ApiKeysConfig, EmailConfig


class TestAppConfig:
    def test_default_config(self):
        config = AppConfig()
        assert config.schedule.timezone == "America/New_York"
        assert config.schedule.delivery_time == "07:00"
        assert config.llm.provider == "anthropic"

    def test_llm_default_model(self):
        config = AppConfig()
        assert "claude" in config.llm.model.lower() or "haiku" in config.llm.model.lower()


class TestLLMConfig:
    def test_set_and_get_api_key(self):
        llm = LLMConfig()
        llm.set_api_key("anthropic", "sk-test-key")
        assert llm.get_api_key("anthropic") == "sk-test-key"

    def test_get_api_key_returns_none_when_not_set(self):
        llm = LLMConfig()
        assert llm.get_api_key("nonexistent_provider") is None

    def test_get_api_key_no_env_fallback(self):
        """After removing env fallback, unset keys must return None."""
        llm = LLMConfig()
        assert llm.get_api_key("anthropic") is None

    def test_api_key_display(self):
        llm = LLMConfig()
        llm.set_api_key("anthropic", "sk-ant-1234567890")
        display = llm.api_key_display("anthropic")
        assert "1234567890" not in display
        assert display.startswith("sk-")

    def test_api_key_display_empty_when_not_set(self):
        llm = LLMConfig()
        assert llm.api_key_display("anthropic") == ""


class TestApiKeysConfig:
    def test_set_and_get(self):
        keys = ApiKeysConfig()
        keys.set_key("newsapi", "test-newsapi")
        assert keys.newsapi == "test-newsapi"

    def test_none_when_not_set(self):
        keys = ApiKeysConfig()
        assert keys.alpha_vantage is None
        assert keys.newsapi is None

    def test_key_display(self):
        keys = ApiKeysConfig()
        keys.set_key("newsapi", "abcd1234efgh5678")
        display = keys.key_display("newsapi")
        assert display.startswith("abcd")
        assert display.endswith("5678")
        assert "****" in display


class TestEmailConfig:
    def test_credentials_not_set(self):
        email = EmailConfig()
        assert email.username is None
        assert email.password is None

    def test_set_credentials(self):
        email = EmailConfig()
        email.set_credential("username", "user@test.com")
        email.set_credential("password", "pass123")
        assert email.username == "user@test.com"
        assert email.password == "pass123"
