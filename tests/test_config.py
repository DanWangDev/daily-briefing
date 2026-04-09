from __future__ import annotations

from briefing.config import AppConfig, LLMConfig


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
        # Clear any env vars that might interfere
        key = llm.get_api_key("nonexistent_provider")
        assert key is None

    def test_api_key_display(self):
        llm = LLMConfig()
        llm.set_api_key("anthropic", "sk-ant-1234567890")
        display = llm.api_key_display("anthropic")
        assert "1234567890" not in display
        assert display.startswith("sk-")
