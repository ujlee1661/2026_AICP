from __future__ import annotations

import asyncio
import json
import os
import re
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
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or config.OPENROUTER_API_KEY
        self.base_url = base_url or config.OPENROUTER_BASE_URL
        self.model = model or config.OPENROUTER_MODEL
        self.max_retries = max_retries
        self.timeout = timeout
        self.offline = os.getenv("TWINMARKET_OFFLINE_LLM", "").strip().lower() in {"1", "true", "yes"}
        if self.offline:
            self.client = None
            return
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")
        if AsyncOpenAI is None:
            raise RuntimeError("openai package is not installed. Run pip install -r requirements.txt.")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=timeout)

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> Any:
        if os.getenv("TWINMARKET_OFFLINE_LLM", "").strip().lower() in {"1", "true", "yes"}:
            return _offline_response(messages)

        kwargs: dict[str, Any] = {
            "model": model or self.model,
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
                return await asyncio.wait_for(
                    self.client.chat.completions.create(**kwargs),
                    timeout=self.timeout + 5,
                )
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
        return response_content(response)


def response_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            return str(message.get("content") or "")
        return ""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "")


def _offline_response(messages: list[dict[str, str]]) -> str:
    prompt = messages[-1].get("content", "") if messages else ""
    if "selected_post_ids" in prompt:
        limit_match = re.search(r"최대\s+(\d+)개", prompt)
        limit = int(limit_match.group(1)) if limit_match else 3
        post_ids = [int(value) for value in re.findall(r"post_id=(\d+)", prompt)]
        return json.dumps({"selected_post_ids": post_ids[:limit]}, ensure_ascii=False)
    if '"reactions"' in prompt:
        post_ids = [int(value) for value in re.findall(r"post_id=(\d+)", prompt)]
        reactions = [
            {"post_id": post_id, "reaction": ("like" if index % 3 == 0 else "none")}
            for index, post_id in enumerate(post_ids)
        ]
        return json.dumps({"reactions": reactions}, ensure_ascii=False)
    if "will_post" in prompt or "게시글 타입 6종" in prompt:
        return json.dumps(
            {
                "will_post": True,
                "post_type": "impression",
                "title": "오늘 삼성전자 흐름 메모",
                "content": "가격 흐름과 뉴스가 엇갈려 보입니다. 무리하지 않고 수량을 제한해 대응하겠습니다.",
            },
            ensure_ascii=False,
        )
    if "오늘 아침 읽은 종목토론방" in prompt or "Best 게시글" in prompt:
        return "커뮤니티는 혼조 분위기입니다. 가격 리스크와 장기 성장성을 함께 보겠습니다."
    if "거래 제약:" in prompt and "최종 결정을 출력" in prompt:
        constraints = _extract_json_after_label(prompt, "거래 제약:")
        allowed = constraints.get("allowed_actions") or ["buy"]
        action = "buy" if "buy" in allowed else "sell"
        max_quantity = int(constraints.get("max_buy_quantity" if action == "buy" else "max_sell_quantity") or 1)
        quantity = max(1, min(max_quantity, 10))
        return json.dumps(
            {
                "action": action,
                "quantity": quantity,
                "reason": "Offline smoke run: mixed signals justify a small constrained trade.",
                "risk_control": "Keep position size small and preserve cash for later turns.",
            },
            ensure_ascii=False,
        )
    if "거래 전 시장 분석" in prompt:
        return json.dumps(
            {
                "market_view": "Mixed short-term setup with both price risk and recovery potential.",
                "valuation_view": "Valuation is not decisive in this offline smoke run.",
                "technical_view": "Price and volume signals are treated as mixed.",
                "news_view": "News impact is mixed and requires cautious sizing.",
                "portfolio_view": "Portfolio risk is managed through small order size.",
                "key_risks": ["volatility", "news uncertainty"],
                "opportunity": ["limited entry after weakness"],
                "caution": ["avoid excessive concentration"],
                "confidence": "medium",
            },
            ensure_ascii=False,
        )
    if "Belief를 JSON" in prompt or "투자 Belief를 JSON" in prompt:
        return json.dumps(
            {
                "dim_1": "Short-term direction is mixed, so I will respond cautiously.",
                "dim_2": "Valuation needs confirmation from market data.",
                "dim_3": "Macro and semiconductor cycle signals remain important.",
                "dim_4": "Investor sentiment looks mixed rather than one-sided.",
                "dim_5": "News flow supports caution and selective action.",
                "dim_6": "I should avoid overconfidence and keep trades small.",
                "belief_summary": "Samsung Electronics has mixed signals today. I will trade conservatively within constraints.",
                "view_change": "Maintained a cautious view based on mixed information.",
            },
            ensure_ascii=False,
        )
    if "pre_search" in prompt:
        return json.dumps(
            {
                "search_needed": False,
                "key_findings": "Offline smoke run uses the base news context only.",
                "curiosity_points": [],
                "search_rationale": "",
                "search_keywords": [],
            },
            ensure_ascii=False,
        )
    if "post_search" in prompt:
        return json.dumps(
            {
                "new_findings": "",
                "view_change": "유지",
                "view_change_detail": "Offline smoke run did not add search results.",
                "unresolved_questions": [],
            },
            ensure_ascii=False,
        )
    if "뉴스" in prompt:
        return json.dumps(
            {
                "selected_news": [],
                "news_sentiment": "mixed",
                "short_term_impact": "Short-term impact is mixed.",
                "long_term_impact": "Long-term impact depends on earnings and semiconductor demand.",
                "persona_interpretation": "The investor stays cautious and avoids oversized trades.",
                "confidence": "medium",
                "reason": "Offline smoke run summary.",
            },
            ensure_ascii=False,
        )
    return "pong"


def _extract_json_after_label(prompt: str, label: str) -> dict[str, Any]:
    start = prompt.find(label)
    if start < 0:
        return {}
    start = prompt.find("{", start)
    if start < 0:
        return {}
    depth = 0
    for index in range(start, len(prompt)):
        char = prompt[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(prompt[start : index + 1])
                except json.JSONDecodeError:
                    return {}
                return data if isinstance(data, dict) else {}
    return {}
