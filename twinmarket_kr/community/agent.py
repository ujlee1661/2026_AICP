from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from twinmarket_kr.agents.memory_agent import MemoryAgent
from twinmarket_kr.db.connection import connect, init_sim_db


ANIMAL_CODES = ["황소", "곰", "독수리", "여우", "늑대", "사자", "호랑이", "코끼리", "펭귄", "돌고래"]


class CommunityAgent:
    def __init__(self, db_path: Path | str) -> None:
        self._db = db_path
        init_sim_db(self._db)

    def generate_anonymous_code(self, agent_id: str) -> str:
        h = int(hashlib.md5(str(agent_id).encode()).hexdigest(), 16)
        animal = ANIMAL_CODES[h % len(ANIMAL_CODES)]
        number = h % 9000 + 1000
        return f"{animal}-{number}"

    def save_post(
        self,
        agent_id: str,
        turn: int,
        date: str,
        post_type: str,
        title: str,
        content: str,
    ) -> int:
        anonymous_code = self.generate_anonymous_code(agent_id)
        with connect(self._db) as conn:
            cur = conn.execute(
                """
                INSERT INTO community_posts (
                    agent_id, anonymous_code, turn, date, post_type, title, content
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (agent_id, anonymous_code, int(turn), date, post_type, title, content),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_today_posts(self, date: str) -> list[dict[str, Any]]:
        with connect(self._db) as conn:
            rows = conn.execute(
                """
                SELECT post_id, agent_id, anonymous_code, post_type, title,
                       like_count, unlike_count, score
                FROM community_posts
                WHERE date = ?
                ORDER BY post_id
                """,
                (date,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_post_content(self, post_id: int) -> dict[str, Any]:
        with connect(self._db) as conn:
            row = conn.execute("SELECT * FROM community_posts WHERE post_id = ?", (int(post_id),)).fetchone()
        return dict(row) if row else {}

    def get_author_profile(self, author_agent_id: str, memory_agent: MemoryAgent, turn: int) -> dict[str, Any]:
        portfolio = memory_agent._latest_portfolio(author_agent_id, before_or_at_turn=turn)
        recent_trades = self._get_recent_trades(author_agent_id, n=3)
        return {
            "portfolio_summary": dict(portfolio) if portfolio else {},
            "recent_trades": recent_trades,
        }

    def _get_recent_trades(self, agent_id: str, n: int = 3) -> list[dict[str, Any]]:
        with connect(self._db) as conn:
            rows = conn.execute(
                """
                SELECT turn, date, action, stock_code, quantity,
                       executed_price, trade_value, status, filled_quantity,
                       action_reason
                FROM trade_log
                WHERE agent_id = ?
                ORDER BY turn DESC
                LIMIT ?
                """,
                (agent_id, int(n)),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_reaction(self, agent_id: str, post_id: int, turn: int, date: str, reaction: str) -> bool:
        normalized = "read" if reaction == "none" else reaction
        if normalized not in {"like", "unlike", "read"}:
            normalized = "read"
        with connect(self._db) as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO community_interactions (
                    agent_id, post_id, turn, date, reaction
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (agent_id, int(post_id), int(turn), date, normalized),
            )
            conn.commit()
            return cur.rowcount > 0

    def update_post_score_live(self, post_id: int, reaction: str) -> None:
        if reaction == "like":
            sql = "UPDATE community_posts SET like_count = like_count + 1, score = score + 1 WHERE post_id = ?"
        elif reaction == "unlike":
            sql = "UPDATE community_posts SET unlike_count = unlike_count + 1, score = score - 1 WHERE post_id = ?"
        else:
            return
        with connect(self._db) as conn:
            conn.execute(sql, (int(post_id),))
            conn.commit()

    def mark_best_posts(self, date: str, n: int) -> list[dict[str, Any]]:
        with connect(self._db) as conn:
            rows = conn.execute(
                """
                SELECT post_id, title, post_type, score
                FROM community_posts
                WHERE date = ?
                ORDER BY score DESC, like_count DESC, post_id ASC
                LIMIT ?
                """,
                (date, int(n)),
            ).fetchall()
            best_ids = [int(row["post_id"]) for row in rows]
            conn.execute("UPDATE community_posts SET is_best = 0 WHERE date = ?", (date,))
            if best_ids:
                placeholders = ",".join("?" * len(best_ids))
                conn.execute(f"UPDATE community_posts SET is_best = 1 WHERE post_id IN ({placeholders})", best_ids)
            conn.commit()
        return [dict(row) for row in rows]

    def save_community_log(
        self,
        agent_id: str,
        turn: int,
        date: str,
        best_posts: list[dict[str, Any]],
        posts_read: list[dict[str, Any]],
        thinking: str,
    ) -> None:
        with connect(self._db) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO community_logs (
                    agent_id, turn, date, best_posts_seen, posts_read, community_thinking
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    int(turn),
                    date,
                    json.dumps(best_posts, ensure_ascii=False),
                    json.dumps(posts_read, ensure_ascii=False),
                    thinking,
                ),
            )
            conn.commit()

    def update_community_thinking(self, agent_id: str, turn: int, thinking: str) -> None:
        with connect(self._db) as conn:
            conn.execute(
                """
                UPDATE community_logs
                SET community_thinking = ?
                WHERE agent_id = ? AND turn = ?
                """,
                (thinking, agent_id, int(turn)),
            )
            conn.commit()

    def get_community_log(self, agent_id: str, turn: int) -> dict[str, Any] | None:
        with connect(self._db) as conn:
            row = conn.execute(
                "SELECT * FROM community_logs WHERE agent_id = ? AND turn = ?",
                (agent_id, int(turn)),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["best_posts_seen"] = json.loads(data.get("best_posts_seen") or "[]")
        data["posts_read"] = json.loads(data.get("posts_read") or "[]")
        return data
