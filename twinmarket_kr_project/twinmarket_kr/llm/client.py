from __future__ import annotations

import asyncio
from typing import Any

try:
    from openai import AsyncOpenAI
except ModuleNotFoundError:
    AsyncOpenAI = None  # type: ignore[assignment]

import config


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or config.OPENROUTER_API_KEY
        self.base_url = base_url or config.OPENROUTER_BASE_URL
        self.model = model or config.OPENROUTER_MODEL
        self.max_retries = max_retries
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")
        if AsyncOpenAI is None:
            raise RuntimeError("openai package is not installed. Run pip install -r requirements.txt.")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if response_format is not None:
            kwargs["response_format"] = response_format

        delay = 1.0
        last_error: Exception | None = None
        for _ in range(self.max_retries):
            try:
                return await self.client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError(f"OpenRouter chat failed after retries: {last_error}") from last_error

    async def ping(self) -> str:
        response = await self.chat(
            [{"role": "user", "content": "Reply with pong."}],
            temperature=0,
        )
        return response.choices[0].message.content or ""
