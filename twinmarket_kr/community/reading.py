from __future__ import annotations

import json
from typing import Any

import config
from twinmarket_kr.llm.analysis import parse_json_loose
from twinmarket_kr.llm.belief import load_prompt
from twinmarket_kr.llm.client import OpenRouterClient, response_content


async def community_reading_select(
    agent: dict[str, Any],
    post_list: list[dict[str, Any]],
    read_limit: int,
    client: OpenRouterClient | None = None,
) -> list[int]:
    client = client or OpenRouterClient()
    if not post_list:
        return []
    prompt_template = load_prompt("community_reading.txt")
    prompt = prompt_template.format(
        mode="select",
        persona_prompt=agent.get("persona_prompt", ""),
        post_list_str=_format_post_list(post_list),
        read_limit=int(read_limit),
        posts_content_str="",
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        model=config.OPENROUTER_COMMUNITY_MODEL,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    raw = parse_json_loose(response_content(response) or "{}")
    selected: list[int] = []
    available = {int(post["post_id"]) for post in post_list}
    for post_id in raw.get("selected_post_ids") or []:
        try:
            pid = int(post_id)
        except (TypeError, ValueError):
            continue
        if pid in available and pid not in selected:
            selected.append(pid)
        if len(selected) >= read_limit:
            break
    return selected


async def community_reading_react(
    agent: dict[str, Any],
    posts_content: list[dict[str, Any]],
    client: OpenRouterClient | None = None,
) -> list[dict[str, Any]]:
    client = client or OpenRouterClient()
    if not posts_content:
        return []
    prompt_template = load_prompt("community_reading.txt")
    prompt = prompt_template.format(
        mode="react",
        persona_prompt=agent.get("persona_prompt", ""),
        post_list_str="",
        read_limit=len(posts_content),
        posts_content_str=_format_posts_content(posts_content),
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        model=config.OPENROUTER_COMMUNITY_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = parse_json_loose(response_content(response) or "{}")
    available = {int(post["post_id"]) for post in posts_content}
    validated: list[dict[str, Any]] = []
    for item in raw.get("reactions") or []:
        try:
            post_id = int(item.get("post_id"))
        except (AttributeError, TypeError, ValueError):
            continue
        reaction = str(item.get("reaction") or "none")
        if post_id in available and reaction in {"like", "unlike", "none"}:
            validated.append({"post_id": post_id, "reaction": reaction})
    return validated


def _format_post_list(post_list: list[dict[str, Any]]) -> str:
    lines = []
    for post in post_list:
        badges = ", ".join(post.get("author_badges") or []) or "없음"
        lines.append(
            f"[post_id={post['post_id']}] [{post.get('post_type', '')}] {post.get('title', '')} "
            f"| 작성자: {post.get('anonymous_code', '')} [{badges}] "
            f"| like {post.get('like_count', 0)} / unlike {post.get('unlike_count', 0)}"
        )
    return "\n".join(lines)


def _format_posts_content(posts_content: list[dict[str, Any]]) -> str:
    parts = []
    for post in posts_content:
        profile_text = ""
        if post.get("author_profile"):
            profile_text = "\n[작성자 프로필] " + json.dumps(
                post["author_profile"], ensure_ascii=False, default=str
            )[:800]
        parts.append(
            f"--- post_id={post['post_id']} [{post.get('post_type', '')}] ---\n"
            f"제목: {post.get('title', '')}\n"
            f"본문: {post.get('content', '')}"
            f"{profile_text}"
        )
    return "\n\n".join(parts)
