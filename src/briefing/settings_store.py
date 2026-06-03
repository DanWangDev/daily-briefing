"""Persist and retrieve app settings from the database with Fernet encryption for secrets."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from briefing.config import AppConfig
from briefing.models import Setting

logger = logging.getLogger(__name__)

_SECRET_KEY_FILE = Path("data/.secret_key")
_ENV_VAR = "BRIEFING_SECRET_KEY"

# Keys that contain credentials and must be encrypted at rest.
SECRET_KEYS = frozenset({
    "llm.api_key.anthropic",
    "llm.api_key.openai",
    "llm.api_key.qwen",
    "llm.api_key.deepseek",
    "api_keys.newsapi",
    "api_keys.alpha_vantage",
    "api_keys.massive",
    "email.username",
    "email.password",
})

# All settings keys we persist (secrets + plain config).
_PLAIN_KEYS = [
    "schedule.timezone",
    "schedule.delivery_time",
    "schedule.email_enabled",
    "llm.provider",
    "llm.model",
    "llm.base_url",
    "email.smtp_host",
    "email.smtp_port",
    "email.from_address",
    "email.to_address",
]


def _derive_key() -> bytes:
    """Derive a stable Fernet key that survives container recreation.

    Resolution order:
      1. ``BRIEFING_SECRET_KEY`` env var — deployment-controlled, takes priority
         so ops can rotate keys without touching files.
      2. ``data/.secret_key`` file — generated once on first run and kept inside
         the persistent data volume, so Docker recreations preserve it.
      3. Fresh generation — cryptographically random 32 bytes, written to the
         file above for all subsequent runs.

    This is NOT a password-grade secret — it prevents casual reading of the
    SQLite file, but anyone with file-system access to the data volume can
    reproduce the key. For a single-user local app this is the same
    trade-off the previous implementation accepted; the improvement is that
    it's now stable across container restarts.
    """
    env_seed = os.environ.get(_ENV_VAR)
    if env_seed:
        digest = hashlib.sha256(env_seed.encode()).digest()
        return base64.urlsafe_b64encode(digest)

    if _SECRET_KEY_FILE.exists():
        try:
            raw = _SECRET_KEY_FILE.read_bytes().strip()
            if raw:
                digest = hashlib.sha256(raw).digest()
                return base64.urlsafe_b64encode(digest)
        except OSError as e:
            logger.warning("Could not read %s: %s — regenerating", _SECRET_KEY_FILE, e)

    # First run (or unreadable file): generate and persist a fresh key.
    _SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw = secrets.token_bytes(32)
    _SECRET_KEY_FILE.write_bytes(raw)
    try:
        os.chmod(_SECRET_KEY_FILE, 0o600)
    except OSError:
        # Windows or filesystems that don't support POSIX perms — best-effort only.
        pass
    logger.info("Generated new secret key at %s", _SECRET_KEY_FILE)
    digest = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_key())


def _encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


def save_settings(session: Session, config: AppConfig) -> None:
    """Write all current config values to the settings table."""
    pairs: list[tuple[str, str, bool]] = []

    # Plain settings
    pairs.append(("ui.language", config.language, False))
    pairs.append(("ui.theme", config.theme, False))
    pairs.append(("ui.tts_voice", config.tts_voice, False))
    pairs.append(("schedule.timezone", config.schedule.timezone, False))
    pairs.append(("schedule.delivery_time", config.schedule.delivery_time, False))
    pairs.append(("schedule.email_enabled", str(config.schedule.email_enabled), False))
    pairs.append(("llm.provider", config.llm.provider, False))
    pairs.append(("llm.model", config.llm.model, False))
    pairs.append(("llm.base_url", config.llm.base_url or "", False))
    pairs.append(("email.smtp_host", config.email.smtp_host, False))
    pairs.append(("email.smtp_port", str(config.email.smtp_port), False))
    pairs.append(("email.from_address", config.email.from_address, False))
    pairs.append(("email.to_address", config.email.to_address, False))

    # Secrets — only persist if non-empty
    secret_sources = {
        "llm.api_key.anthropic": config.llm.get_api_key("anthropic"),
        "llm.api_key.openai": config.llm.get_api_key("openai"),
        "llm.api_key.qwen": config.llm.get_api_key("qwen"),
        "llm.api_key.deepseek": config.llm.get_api_key("deepseek"),
        "api_keys.newsapi": config.api_keys.newsapi,
        "api_keys.alpha_vantage": config.api_keys.alpha_vantage,
        "api_keys.massive": config.api_keys.massive,
        "email.username": config.email.username,
        "email.password": config.email.password,
    }
    for key, value in secret_sources.items():
        if value:
            pairs.append((key, _encrypt(value), True))

    for key, value, is_secret in pairs:
        existing = session.get(Setting, key)
        if existing:
            existing.value = value
            existing.is_secret = is_secret
        else:
            session.add(Setting(key=key, value=value, is_secret=is_secret))

    session.commit()


def load_settings(session: Session, config: AppConfig) -> None:
    """Hydrate an AppConfig from persisted settings.  Skips missing keys."""
    rows: list[Setting] = session.query(Setting).all()
    store = {row.key: row for row in rows}

    def _get(key: str) -> str | None:
        row = store.get(key)
        if row is None:
            return None
        if row.is_secret:
            try:
                return _decrypt(row.value)
            except Exception:
                logger.warning("Failed to decrypt setting %s — skipping", key)
                return None
        return row.value

    # Language, theme & TTS
    if v := _get("ui.language"):
        config.language = v
    if v := _get("ui.theme"):
        config.theme = v
    if (v := _get("ui.tts_voice")) is not None:
        config.tts_voice = v

    # Schedule
    if v := _get("schedule.timezone"):
        config.schedule.timezone = v
    if v := _get("schedule.delivery_time"):
        config.schedule.delivery_time = v
    if v := _get("schedule.email_enabled"):
        config.schedule.email_enabled = v.lower() == "true"

    # LLM
    if v := _get("llm.provider"):
        config.llm.provider = v
    if v := _get("llm.model"):
        config.llm.model = v
    if (v := _get("llm.base_url")) is not None:
        config.llm.base_url = v or None

    # LLM API keys
    for provider in ("anthropic", "openai", "qwen", "deepseek"):
        if v := _get(f"llm.api_key.{provider}"):
            config.llm.set_api_key(provider, v)

    # Data-source API keys
    if v := _get("api_keys.newsapi"):
        config.api_keys.set_key("newsapi", v)
    if v := _get("api_keys.alpha_vantage"):
        config.api_keys.set_key("alpha_vantage", v)
    if v := _get("api_keys.massive"):
        config.api_keys.set_key("massive", v)

    # Email
    if v := _get("email.smtp_host"):
        config.email.smtp_host = v
    if v := _get("email.smtp_port"):
        config.email.smtp_port = int(v)
    if v := _get("email.from_address"):
        config.email.from_address = v
    if v := _get("email.to_address"):
        config.email.to_address = v
    if v := _get("email.username"):
        config.email.set_credential("username", v)
    if v := _get("email.password"):
        config.email.set_credential("password", v)
