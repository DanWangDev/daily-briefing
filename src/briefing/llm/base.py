from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel

from briefing.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: dict = {}


class BaseLLMProvider(ABC):
    """Common interface for all LLM providers."""

    @abstractmethod
    async def complete(self, system: str, user: str, max_tokens: int = 2000) -> LLMResponse:
        ...

    @abstractmethod
    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 2000) -> dict:
        ...


def create_llm_provider(config: LLMConfig) -> BaseLLMProvider:
    """Factory function to create the configured LLM provider."""
    if not config.provider:
        raise ValueError("No LLM provider configured — select one in Settings")
    if not config.model:
        raise ValueError("No model configured — set a model in Settings")
    match config.provider:
        case "anthropic":
            from briefing.llm.anthropic_provider import AnthropicProvider
            if not config.api_key:
                raise ValueError("Anthropic API key not configured — set it in Settings")
            return AnthropicProvider(api_key=config.api_key, model=config.model)
        case "openai":
            from briefing.llm.openai_provider import OpenAIProvider
            if not config.api_key:
                raise ValueError("OpenAI API key not configured — set it in Settings")
            return OpenAIProvider(api_key=config.api_key, model=config.model)
        case "ollama":
            from briefing.llm.ollama_provider import OllamaProvider
            return OllamaProvider(
                base_url=config.base_url or "http://localhost:11434",
                model=config.model,
            )
        case "qwen":
            from briefing.llm.qwen_provider import QwenProvider
            if not config.api_key:
                raise ValueError("Qwen API key not configured — set it in Settings")
            return QwenProvider(
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            )
        case "deepseek":
            from briefing.llm.deepseek_provider import DeepSeekProvider
            if not config.api_key:
                raise ValueError("DeepSeek API key not configured — set it in Settings")
            return DeepSeekProvider(
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url or "https://api.deepseek.com/v1",
            )
        case _:
            raise ValueError(f"Unknown LLM provider: {config.provider}")
