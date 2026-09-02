import json
from typing import Any, Protocol

import httpx

from app.core.config import Settings


class LLMProviderError(Exception):
    """Raised when the configured model endpoint cannot return a completion."""


class LLMOutputError(Exception):
    """Raised when model output does not satisfy a local contract."""


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float) -> None:
        normalized = base_url.rstrip("/")
        self.endpoint = (
            normalized
            if normalized.endswith("/chat/completions")
            else f"{normalized}/chat/completions"
        )
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.endpoint, headers=headers, json=body)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMProviderError("model request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError("model endpoint request failed") from exc

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMProviderError("model endpoint returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("model endpoint returned empty content")
        return content


def build_llm_provider(settings: Settings) -> LLMProvider | None:
    if not settings.llm_transport_configured:
        return None
    return OpenAICompatibleProvider(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_timeout_seconds,
    )


def parse_json_object(content: str) -> dict[str, Any]:
    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMOutputError("model output is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise LLMOutputError("model output must be a JSON object")
    return payload
