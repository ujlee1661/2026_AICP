from __future__ import annotations

from typing import Any

import config
from twinmarket_kr.llm.analysis import parse_json_loose
from twinmarket_kr.llm.belief import load_prompt
from twinmarket_kr.llm.client import OpenRouterClient, response_content


POST_TYPES = {"impression", "question", "trade_share", "profit_share", "analysis", "column"}

POST_TYPES_GUIDE = """
게시글 타입 6종 (하나를 선택):
- impression  : 짧은 감탄, 단상, 느낌 (1~3문장)
- question    : 다른 투자자에게 의견/정보 질문
- trade_share : 오늘 매수/매도 거래 소개 (반드시 실제 거래를 반영할 필요 없음)
- profit_share: 수익/손실 인증, 수익률 공유
- analysis    : 기술적/뉴스 분석, 시장 전망 (비교적 긴 글)
- column      : 한 편의 칼럼 형식, 긴 호흡의 의견
"""


async def posting_decision(
    agent: dict[str, Any],
    today_belief: dict[str, Any],
    decision: dict[str, Any],
    date: str,
    client: OpenRouterClient | None = None,
) -> dict[str, Any] | None:
    client = client or OpenRouterClient()
    prompt_template = load_prompt("posting_decision.txt")
    trade_summary = (
        f"오늘 거래: {decision.get('action', 'hold')} {decision.get('quantity', 0)}주, "
        f"주문가: {decision.get('price', '')}, 이유: {str(decision.get('reason', ''))[:200]}"
    )
    prompt = prompt_template.format(
        persona_prompt=agent.get("persona_prompt", ""),
        belief_summary=today_belief.get("belief_summary", ""),
        view_change=today_belief.get("view_change", ""),
        trade_summary=trade_summary,
        date=date,
        post_types_guide=POST_TYPES_GUIDE,
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        model=config.OPENROUTER_COMMUNITY_MODEL,
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    raw = parse_json_loose(response_content(response) or "{}")
    if not raw.get("will_post", False):
        return None
    title = str(raw.get("title") or "").strip()
    content = str(raw.get("content") or "").strip()
    if not title or not content:
        return None
    post_type = str(raw.get("post_type") or "impression").strip()
    if post_type not in POST_TYPES:
        post_type = "impression"
    return {"will_post": True, "post_type": post_type, "title": title, "content": content}
