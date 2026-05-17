from __future__ import annotations

import json
import logging

import httpx

from briefing.llm.base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def complete(self, system: str, user: str, max_tokens: int = 2000) -> LLMResponse:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
            )
            data = resp.json()
            return LLMResponse(
                content=data.get("message", {}).get("content", ""),
                model=self._model,
                provider="ollama",
                usage={
                    "input_tokens": data.get("prompt_eval_count", 0),
                    "output_tokens": data.get("eval_count", 0),
                },
            )

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 2000) -> dict:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system + "\n\nRespond with valid JSON only."},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"num_predict": max_tokens},
                },
            )
            data = resp.json()
            text = data.get("message", {}).get("content", "{}")
            return json.loads(text)
