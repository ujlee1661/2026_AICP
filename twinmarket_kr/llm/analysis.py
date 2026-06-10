from __future__ import annotations

import json
from typing import Any

from twinmarket_kr.llm.belief import load_prompt
from twinmarket_kr.llm.client import OpenRouterClient, response_content


NEWS_INTERPRETATION_KEYS = (
    "selected_news",
    "news_sentiment",
    "short_term_impact",
    "long_term_impact",
    "persona_interpretation",
    "confidence",
    "reason",
)

MARKET_ANALYSIS_KEYS = (
    "market_view",
    "valuation_view",
    "technical_view",
    "news_view",
    "portfolio_view",
    "key_risks",
    "opportunity",
    "caution",
    "confidence",
)

DEPTH2_PRE_SEARCH_KEYS = (
    "search_needed",
    "key_findings",
    "curiosity_points",
    "search_rationale",
    "search_keywords",
)

DEPTH2_POST_SEARCH_KEYS = (
    "new_findings",
    "view_change",
    "view_change_detail",
    "unresolved_questions",
)


def parse_json_object(content: str, required_keys: tuple[str, ...], label: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    data = json.loads(text)
    missing = [key for key in required_keys if key not in data]
    if missing:
        raise ValueError(f"{label} JSON missing keys: {missing}")
    return data


async def interpret_news(
    agent: dict[str, Any],
    news_context: dict[str, Any],
    *,
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    client = client or OpenRouterClient()
    prompt = load_prompt("news_interpretation.txt").format(
        persona_prompt=agent["persona_prompt"],
        news_context=json.dumps(news_context, ensure_ascii=False, indent=2),
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return parse_json_object(
        response_content(response) or "{}",
        NEWS_INTERPRETATION_KEYS,
        "news interpretation",
    )


async def depth2_pre_search(
    agent: dict[str, Any],
    base_news_context: dict[str, Any],
    *,
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    client = client or OpenRouterClient()
    prompt = load_prompt("news_agent.txt").format(
        mode="pre_search",
        persona_prompt=agent["persona_prompt"],
        base_news_context=json.dumps(base_news_context, ensure_ascii=False, indent=2),
        search_results="[]",
        pre_search_thinking="{}",
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    data = parse_json_object(
        response_content(response) or "{}",
        DEPTH2_PRE_SEARCH_KEYS,
        "depth2 pre-search",
    )
    raw_needed = data.get("search_needed")
    if isinstance(raw_needed, str):
        data["search_needed"] = raw_needed.strip().lower() in {"true", "yes", "1", "필요", "필요함"}
    else:
        data["search_needed"] = bool(raw_needed)
    if not isinstance(data.get("curiosity_points"), list):
        data["curiosity_points"] = []
    if not isinstance(data.get("search_keywords"), list):
        data["search_keywords"] = []
    data["search_keywords"] = [str(keyword).strip() for keyword in data["search_keywords"] if str(keyword).strip()][:8]
    return data


async def depth2_post_search(
    agent: dict[str, Any],
    base_news_context: dict[str, Any],
    search_results: list[dict[str, Any]],
    pre_thinking: dict[str, Any],
    *,
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    client = client or OpenRouterClient()
    prompt = load_prompt("news_agent.txt").format(
        mode="post_search",
        persona_prompt=agent["persona_prompt"],
        base_news_context=json.dumps(base_news_context, ensure_ascii=False, indent=2),
        search_results=json.dumps(search_results, ensure_ascii=False, indent=2),
        pre_search_thinking=json.dumps(pre_thinking, ensure_ascii=False, indent=2),
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    data = parse_json_object(
        response_content(response) or "{}",
        DEPTH2_POST_SEARCH_KEYS,
        "depth2 post-search",
    )
    if not isinstance(data.get("unresolved_questions"), list):
        data["unresolved_questions"] = []
    return data


async def analyze_market(
    agent: dict[str, Any],
    *,
    today_belief: dict[str, Any],
    market_features: dict[str, Any],
    portfolio_summary: str,
    news_interpretation: dict[str, Any],
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    client = client or OpenRouterClient()
    prompt = load_prompt("market_analysis.txt").format(
        persona_prompt=agent["persona_prompt"],
        today_belief=json.dumps(today_belief, ensure_ascii=False, indent=2),
        market_features=json.dumps(market_features, ensure_ascii=False, indent=2),
        portfolio_summary=portfolio_summary,
        news_interpretation=json.dumps(news_interpretation, ensure_ascii=False, indent=2),
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return parse_json_object(
        response_content(response) or "{}",
        MARKET_ANALYSIS_KEYS,
        "market analysis",
    )
