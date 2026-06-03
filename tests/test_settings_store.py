from __future__ import annotations

from briefing.config import AppConfig
from briefing.database import init_db, get_session
from briefing.settings_store import (
    _encrypt,
    _decrypt,
    save_settings,
    load_settings,
)


def _make_config() -> AppConfig:
    config = AppConfig()
    config.database.path = ":memory:"
    return config


class TestEncryption:
    def test_round_trip(self):
        assert _decrypt(_encrypt("super-secret-key")) == "super-secret-key"

    def test_ciphertext_differs_from_plaintext(self):
        ct = _encrypt("my-api-key")
        assert ct != "my-api-key"


class TestSaveAndLoad:
    def test_plain_settings_round_trip(self):
        config = _make_config()
        init_db(config)

        config.schedule.timezone = "Europe/London"
        config.schedule.delivery_time = "09:30"
        config.llm.provider = "openai"
        config.llm.model = "gpt-4o"

        with get_session() as session:
            save_settings(session, config)

        fresh = _make_config()
        with get_session() as session:
            load_settings(session, fresh)

        assert fresh.schedule.timezone == "Europe/London"
        assert fresh.schedule.delivery_time == "09:30"
        assert fresh.llm.provider == "openai"
        assert fresh.llm.model == "gpt-4o"

    def test_secret_keys_round_trip(self):
        config = _make_config()
        init_db(config)

        config.llm.set_api_key("anthropic", "sk-ant-abc123")
        config.llm.set_api_key("openai", "sk-openai-xyz")
        config.api_keys.set_key("newsapi", "newsapi-key-789")
        config.api_keys.set_key("alpha_vantage", "av-key-456")

        with get_session() as session:
            save_settings(session, config)

        fresh = _make_config()
        with get_session() as session:
            load_settings(session, fresh)

        assert fresh.llm.get_api_key("anthropic") == "sk-ant-abc123"
        assert fresh.llm.get_api_key("openai") == "sk-openai-xyz"
        assert fresh.api_keys.newsapi == "newsapi-key-789"
        assert fresh.api_keys.alpha_vantage == "av-key-456"

    def test_email_credentials_round_trip(self):
        config = _make_config()
        init_db(config)

        config.email.set_credential("username", "user@example.com")
        config.email.set_credential("password", "s3cret")
        config.email.smtp_host = "mail.example.com"
        config.email.smtp_port = 465

        with get_session() as session:
            save_settings(session, config)

        fresh = _make_config()
        with get_session() as session:
            load_settings(session, fresh)

        assert fresh.email.username == "user@example.com"
        assert fresh.email.password == "s3cret"
        assert fresh.email.smtp_host == "mail.example.com"
        assert fresh.email.smtp_port == 465

    def test_overwrite_on_second_save(self):
        config = _make_config()
        init_db(config)

        config.llm.provider = "anthropic"
        with get_session() as session:
            save_settings(session, config)

        config.llm.provider = "qwen"
        with get_session() as session:
            save_settings(session, config)

        fresh = _make_config()
        with get_session() as session:
            load_settings(session, fresh)

        assert fresh.llm.provider == "qwen"

    def test_empty_secrets_not_persisted(self):
        """Keys that are None/empty should not create DB rows."""
        config = _make_config()
        init_db(config)

        # Don't set any API keys
        with get_session() as session:
            save_settings(session, config)

        fresh = _make_config()
        with get_session() as session:
            load_settings(session, fresh)

        assert fresh.llm.get_api_key("anthropic") is None
        assert fresh.api_keys.newsapi is None

    def test_deepseek_api_key_round_trip(self):
        """DeepSeek provider key must survive save/load cycle."""
        config = _make_config()
        init_db(config)

        config.llm.set_api_key("deepseek", "sk-deepseek-123")
        config.llm.provider = "deepseek"
        config.llm.model = "deepseek-chat"

        with get_session() as session:
            save_settings(session, config)

        fresh = _make_config()
        with get_session() as session:
            load_settings(session, fresh)

        assert fresh.llm.get_api_key("deepseek") == "sk-deepseek-123"
        assert fresh.llm.provider == "deepseek"
        assert fresh.llm.model == "deepseek-chat"

    def test_secrets_stored_encrypted(self):
        """The raw DB value for a secret should not be the plaintext."""
        config = _make_config()
        init_db(config)

        config.llm.set_api_key("anthropic", "sk-ant-plaintext")
        with get_session() as session:
            save_settings(session, config)

        from briefing.models import Setting

        with get_session() as session:
            row = session.get(Setting, "llm.api_key.anthropic")
            assert row is not None
            assert row.is_secret
            assert row.value != "sk-ant-plaintext"
