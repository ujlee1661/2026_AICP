# Community 기능 코드 구현 플랜 (Community_Code_Plan.md)

> **참조 설계 문서**: `Community_ReProposal.md`  
> **기존 코드 기준**: `Code_Plan.md`, 현재 구현된 `twinmarket_kr/` 소스코드  
> **작성 목적**: Code Agent가 이 문서 하나만 보고 Community 기능을 단계별로 구현할 수 있도록 하는 가이드라인

---

## 0. 이 문서를 읽는 Code Agent에게

### 새 세션 시작 시
1. 이 문서(`Community_Code_Plan.md`) 전체를 읽는다.
2. `Community_ReProposal.md`를 읽어 설계 의도와 목적을 파악한다.
3. `Code_Plan.md`의 **"진행 로그"** 섹션에서 기존 구현 상태를 확인한다.
4. 아래 **Step별 체크리스트**에서 아직 완료되지 않은 Step부터 시작한다.

### Step 완료 시 (반드시)
- 이 문서 맨 아래 **"진행 로그"** 섹션에 완료 노트를 추가한다.
- 계획과 달라진 결정은 `Code_Status.md`에 기록한다.

### Community 기능이 추가/수정하는 원칙
- 기존 코드(`daily_cycle.py`, `simulation.py`, `collect_context.py`)는 **최소한만 수정**한다.
- Community 신규 로직은 최대한 `twinmarket_kr/community/` 패키지 안에 캡슐화한다.
- `config.ENABLE_COMMUNITY = False`이면 기존 코드와 동일하게 동작해야 한다.

---

## 1. 변경 파일 전체 지도

### 신규 생성 파일

| 파일 경로 | 역할 |
|-----------|------|
| `twinmarket_kr/community/__init__.py` | 패키지 init |
| `twinmarket_kr/community/agent.py` | CommunityAgent — DB read/write 전담 |
| `twinmarket_kr/community/badge.py` | 뱃지 계산 (LLM 없음, 규칙 기반) |
| `twinmarket_kr/community/thinking.py` | `community_thinking()` LLM 함수 |
| `twinmarket_kr/community/posting.py` | `posting_decision()` LLM 함수 |
| `twinmarket_kr/community/reading.py` | `community_reading_select()` + `community_reading_react()` LLM 함수 |
| `prompts/community_thinking.txt` | Community Thinking 프롬프트 |
| `prompts/posting_decision.txt` | 게시글 작성 결정 프롬프트 |
| `prompts/community_reading.txt` | 게시글 선택·반응 프롬프트 (mode 파라미터) |

### 수정되는 기존 파일

| 파일 경로 | 변경 내용 |
|-----------|-----------|
| `twinmarket_kr/db/schema.py` | community 테이블 3개 DDL 추가 |
| `config.py` | Community Settings 블록 추가 |
| `twinmarket_kr/core/collect_context.py` | `community_log` 수집 로직 추가 |
| `twinmarket_kr/core/daily_cycle.py` | `community_thinking` + `posting_decision` 단계 추가 |
| `twinmarket_kr/simulation.py` | `community_phase()` 함수 추가 및 메인 루프에 삽입 |
| `prompts/update_belief.txt` | `community_thinking` 입력 변수 추가 |

---

## 2. Step 1 — DB 스키마 추가

**파일**: `twinmarket_kr/db/schema.py`

기존 `SIM_DDLS` 리스트 끝에 아래 3개 DDL을 추가한다. 기존 테이블 정의는 건드리지 않는다.

### 2-1. community_posts 테이블

```sql
CREATE TABLE IF NOT EXISTS community_posts (
    post_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id      TEXT    NOT NULL,
    anonymous_code TEXT   NOT NULL,
    turn          INTEGER NOT NULL,
    date          TEXT    NOT NULL,
    post_type     TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    content       TEXT    NOT NULL,
    like_count    INTEGER NOT NULL DEFAULT 0,
    unlike_count  INTEGER NOT NULL DEFAULT 0,
    score         INTEGER NOT NULL DEFAULT 0,
    is_best       INTEGER NOT NULL DEFAULT 0
)
```

- `post_type`: `impression` / `question` / `trade_share` / `profit_share` / `analysis` / `column`
- `score` = `like_count - unlike_count` (저장 시 자동 계산)
- `is_best`: 하루 Best 게시글 선정 후 1로 갱신

### 2-2. community_interactions 테이블

```sql
CREATE TABLE IF NOT EXISTS community_interactions (
    interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id       TEXT    NOT NULL,
    post_id        INTEGER NOT NULL,
    turn           INTEGER NOT NULL,
    date           TEXT    NOT NULL,
    reaction       TEXT    NOT NULL,
    UNIQUE(agent_id, post_id)
)
```

- `reaction`: `'like'` / `'unlike'` / `'read'` (본문만 읽고 반응 없을 때)
- `UNIQUE(agent_id, post_id)`: 동일 Agent가 같은 글에 두 번 반응하지 않도록 보장

### 2-3. community_logs 테이블

```sql
CREATE TABLE IF NOT EXISTS community_logs (
    log_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id          TEXT    NOT NULL,
    turn              INTEGER NOT NULL,
    date              TEXT    NOT NULL,
    best_posts_seen   TEXT,
    posts_read        TEXT,
    community_thinking TEXT,
    UNIQUE(agent_id, turn)
)
```

- `best_posts_seen`: JSON 문자열 — `[{"post_id": int, "title": str, "post_type": str, "score": int}, ...]`
- `posts_read`: JSON 문자열 — `[{"post_id": int, "title": str, "content": str, "reaction": str, "author_badges": [...], "author_profile": {...} | null}, ...]`
- `community_thinking`: Community Thinking LLM이 생성한 자유 형식 텍스트

### 2-4. _reset_runtime_tables 수정

`simulation.py`의 `_reset_runtime_tables()` 함수에 아래 3줄을 추가한다.

```python
conn.execute("DELETE FROM community_posts")
conn.execute("DELETE FROM community_interactions")
conn.execute("DELETE FROM community_logs WHERE turn > 0")
```

---

## 3. Step 2 — config.py 설정 추가

**파일**: `config.py`

`ensure_directories()` 함수 정의 **바로 위**에 아래 블록을 추가한다.

```python
# ===== Community Settings =====
ENABLE_COMMUNITY: bool = True
ENABLE_COMMUNITY_POSTING: bool = True
ENABLE_COMMUNITY_READING: bool = True

COMMUNITY_DEPTH1_READ_LIMIT: int = 5      # Depth 1 Agent가 본문을 읽을 수 있는 최대 게시글 수
COMMUNITY_DEPTH2_READ_LIMIT: int = 10     # Depth 2 Agent가 본문을 읽을 수 있는 최대 게시글 수
COMMUNITY_BEST_POST_COUNT: int = 5        # 하루 Best 게시글 선정 수

BADGE_TOP_RETURN_PERCENTILE: int = 20     # 상위 수익자 뱃지: 누적 수익률 상위 N%
BADGE_TOP_ASSET_PERCENTILE: int = 20      # 자산가 뱃지: 총평가액 상위 N%
BADGE_INFLUENCER_PERCENTILE: int = 20     # 인플루언서 뱃지: 누적 Like 수 상위 N%

OPENROUTER_COMMUNITY_MODEL: str = os.getenv(
    "OPENROUTER_COMMUNITY_MODEL", "openai/gpt-4o-mini"
)  # Community 활동(포스팅·열람·Thinking)에 사용하는 저렴한 모델
```

**왜 별도 Community 모델인가**: `make_decision()`은 고성능 모델(`OPENROUTER_MODEL`)을 사용한다. Community 활동(포스팅, 열람, Thinking)은 정밀도보다 비용 효율이 중요하므로 저렴한 모델을 별도 지정한다.

---

## 4. Step 3 — twinmarket_kr/community/ 패키지

### 4-1. community/agent.py — CommunityAgent

이 클래스는 Community 관련 모든 DB 읽기·쓰기를 담당한다. `MemoryAgent`와 동일한 패턴으로 설계한다.

```python
# twinmarket_kr/community/agent.py
from __future__ import annotations
import hashlib
import json
from typing import Any

import config
from twinmarket_kr.db.connection import connect
from twinmarket_kr.agents.memory_agent import MemoryAgent


ANIMAL_CODES = ["황소", "곰", "독수리", "여우", "늑대", "사자", "호랑이", "코끼리", "펭귄", "돌고래"]


class CommunityAgent:
    def __init__(self, db_path: str) -> None:
        self._db = db_path

    # ── 익명 코드 ─────────────────────────────────────────────────
    def generate_anonymous_code(self, agent_id: str) -> str:
        """agent_id를 기반으로 결정론적 익명 코드를 생성한다. (예: '황소-3729')"""
        h = int(hashlib.md5(str(agent_id).encode()).hexdigest(), 16)
        animal = ANIMAL_CODES[h % len(ANIMAL_CODES)]
        number = h % 9000 + 1000  # 1000~9999
        return f"{animal}-{number}"

    # ── 게시글 저장 ────────────────────────────────────────────────
    def save_post(
        self,
        agent_id: str,
        turn: int,
        date: str,
        post_type: str,
        title: str,
        content: str,
    ) -> int:
        """게시글을 저장하고 post_id를 반환한다."""
        anonymous_code = self.generate_anonymous_code(agent_id)
        with connect(self._db) as conn:
            cur = conn.execute(
                """INSERT INTO community_posts
                   (agent_id, anonymous_code, turn, date, post_type, title, content)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, anonymous_code, turn, date, post_type, title, content),
            )
            conn.commit()
            return cur.lastrowid

    # ── 게시글 목록 조회 ───────────────────────────────────────────
    def get_today_posts(self, date: str) -> list[dict]:
        """해당 날짜에 올라온 모든 게시글 목록을 반환한다 (본문 제외)."""
        with connect(self._db) as conn:
            rows = conn.execute(
                """SELECT post_id, agent_id, anonymous_code, post_type, title,
                          like_count, unlike_count, score
                   FROM community_posts
                   WHERE date = ?
                   ORDER BY post_id""",
                (date,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_post_content(self, post_id: int) -> dict:
        """특정 게시글의 전체 내용(본문 포함)을 반환한다."""
        with connect(self._db) as conn:
            row = conn.execute(
                "SELECT * FROM community_posts WHERE post_id = ?", (post_id,)
            ).fetchone()
        return dict(row) if row else {}

    # ── 작성자 프로필 (Depth 2용) ──────────────────────────────────
    def get_author_profile(
        self, author_agent_id: str, memory_agent: MemoryAgent, turn: int
    ) -> dict:
        """
        Depth 2 Agent가 작성자 프로필을 조회할 때 사용한다.
        MemoryAgent를 통해 작성자의 최신 포트폴리오와 최근 3턴 거래 내역을 가져온다.
        별도 Tool Call 없이 본문과 함께 자동 제공된다.
        """
        portfolio = memory_agent._latest_portfolio(author_agent_id, before_or_at_turn=turn)
        portfolio_data = dict(portfolio) if portfolio else {}

        recent_trades = memory_agent.get_recent_trades(author_agent_id, n=3)  # 최근 3건
        return {
            "portfolio_summary": portfolio_data,
            "recent_trades": recent_trades,
        }

    # ── 반응 기록 및 Live 점수 갱신 ───────────────────────────────
    def record_reaction(
        self, agent_id: str, post_id: int, turn: int, date: str, reaction: str
    ) -> None:
        """Like/Unlike/Read 반응을 기록한다."""
        with connect(self._db) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO community_interactions
                   (agent_id, post_id, turn, date, reaction)
                   VALUES (?, ?, ?, ?, ?)""",
                (agent_id, post_id, turn, date, reaction),
            )
            conn.commit()

    def update_post_score_live(self, post_id: int, reaction: str) -> None:
        """
        반응이 완료될 때 즉시 해당 게시글의 like/unlike/score를 갱신한다.
        Live 방식 — 나중에 처리되는 Agent는 이미 갱신된 수치를 본다.
        """
        if reaction == "like":
            sql = "UPDATE community_posts SET like_count = like_count + 1, score = score + 1 WHERE post_id = ?"
        elif reaction == "unlike":
            sql = "UPDATE community_posts SET unlike_count = unlike_count + 1, score = score - 1 WHERE post_id = ?"
        else:
            return
        with connect(self._db) as conn:
            conn.execute(sql, (post_id,))
            conn.commit()

    # ── Best 게시글 선정 ───────────────────────────────────────────
    def mark_best_posts(self, date: str, n: int) -> list[dict]:
        """score 기준 상위 N개를 Best 게시글로 표시하고 반환한다."""
        with connect(self._db) as conn:
            rows = conn.execute(
                """SELECT post_id, title, post_type, score
                   FROM community_posts
                   WHERE date = ?
                   ORDER BY score DESC
                   LIMIT ?""",
                (date, n),
            ).fetchall()
            best_ids = [r["post_id"] for r in rows]
            if best_ids:
                placeholders = ",".join("?" * len(best_ids))
                conn.execute(
                    f"UPDATE community_posts SET is_best = 1 WHERE post_id IN ({placeholders})",
                    best_ids,
                )
                conn.commit()
        return [dict(r) for r in rows]

    # ── Community Log 저장/조회 ────────────────────────────────────
    def save_community_log(
        self,
        agent_id: str,
        turn: int,
        date: str,
        best_posts: list[dict],
        posts_read: list[dict],
        thinking: str,
    ) -> None:
        with connect(self._db) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO community_logs
                   (agent_id, turn, date, best_posts_seen, posts_read, community_thinking)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    agent_id,
                    turn,
                    date,
                    json.dumps(best_posts, ensure_ascii=False),
                    json.dumps(posts_read, ensure_ascii=False),
                    thinking,
                ),
            )
            conn.commit()

    def get_community_log(self, agent_id: str, turn: int) -> dict | None:
        """전날(turn-1) community_log를 반환한다. 없으면 None."""
        with connect(self._db) as conn:
            row = conn.execute(
                "SELECT * FROM community_logs WHERE agent_id = ? AND turn = ?",
                (agent_id, turn),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["best_posts_seen"] = json.loads(d["best_posts_seen"] or "[]")
        d["posts_read"] = json.loads(d["posts_read"] or "[]")
        return d
```

**주의**: `memory_agent.get_recent_trades(agent_id, n=3)`는 기존 MemoryAgent에 없을 수 있다. 있으면 그대로 사용하고, 없으면 `trade_log` 테이블에서 직접 쿼리하는 헬퍼를 CommunityAgent 안에 구현한다.

---

### 4-2. community/badge.py — 뱃지 계산

LLM 없이 규칙 기반으로 뱃지를 계산한다. 매 턴마다 호출된다.

```python
# twinmarket_kr/community/badge.py
from __future__ import annotations
import json
from typing import Any

import config
from twinmarket_kr.db.connection import connect
from twinmarket_kr.agents.memory_agent import MemoryAgent


def calculate_badges(
    agents: list[dict[str, Any]],
    memory_agent: MemoryAgent,
    turn: int,
    db_path: str,
) -> dict[str, list[str]]:
    """
    모든 Agent의 뱃지를 계산해 {agent_id: [badge_name, ...]} 형태로 반환한다.
    뱃지 3종: '상위 수익자', '자산가', '커뮤니티 인플루언서'
    """
    n = len(agents)
    badges: dict[str, list[str]] = {str(a["agent_id"]): [] for a in agents}

    # ─ 수익률 데이터 수집 ─
    returns: list[tuple[str, float]] = []
    assets: list[tuple[str, float]] = []
    for agent in agents:
        aid = str(agent["agent_id"])
        row = memory_agent._latest_portfolio(aid, before_or_at_turn=turn)
        if row is None:
            continue
        total_value = float(row.get("total_value") or row.get("cash", 0))
        initial_cash = float(config.INI_CASH_SMALL)  # 기본값; 필요시 agent["initial_cash"]로 교체
        ret = (total_value - initial_cash) / initial_cash
        returns.append((aid, ret))
        assets.append((aid, total_value))

    # ─ 상위 수익자 뱃지 ─
    cutoff = max(1, int(n * config.BADGE_TOP_RETURN_PERCENTILE / 100))
    top_return_ids = {aid for aid, _ in sorted(returns, key=lambda x: -x[1])[:cutoff]}
    for aid in top_return_ids:
        badges[aid].append("상위 수익자")

    # ─ 자산가 뱃지 ─
    cutoff = max(1, int(n * config.BADGE_TOP_ASSET_PERCENTILE / 100))
    top_asset_ids = {aid for aid, _ in sorted(assets, key=lambda x: -x[1])[:cutoff]}
    for aid in top_asset_ids:
        badges[aid].append("자산가")

    # ─ 커뮤니티 인플루언서 뱃지 ─
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT agent_id, SUM(like_count) AS total_likes FROM community_posts GROUP BY agent_id"
        ).fetchall()
    like_counts = [(str(r["agent_id"]), int(r["total_likes"] or 0)) for r in rows]
    if like_counts:
        cutoff = max(1, int(len(like_counts) * config.BADGE_INFLUENCER_PERCENTILE / 100))
        top_influencer_ids = {aid for aid, _ in sorted(like_counts, key=lambda x: -x[1])[:cutoff]}
        for aid in top_influencer_ids:
            if aid in badges:
                badges[aid].append("커뮤니티 인플루언서")

    return badges
```

---

### 4-3. community/thinking.py — Community Thinking LLM

```python
# twinmarket_kr/community/thinking.py
from __future__ import annotations
from typing import Any

import config
from twinmarket_kr.llm.client import OpenRouterClient, response_content
from twinmarket_kr.llm.belief import load_prompt


async def community_thinking(
    agent: dict[str, Any],
    community_log: dict,
    client: OpenRouterClient | None = None,
) -> str:
    """
    전날 커뮤니티 경험(community_log)을 바탕으로 Community Thinking을 생성한다.
    News Thinking(interpret_news)과 병렬로 호출된다.
    반환값: 자유 형식 텍스트 (update_belief의 context에 포함됨)
    """
    if client is None:
        client = OpenRouterClient()

    prompt_template = load_prompt("community_thinking")
    best_posts = community_log.get("best_posts_seen") or []
    posts_read = community_log.get("posts_read") or []

    prompt = prompt_template.format(
        persona_prompt=agent.get("persona_prompt", ""),
        best_posts_summary=_format_best_posts(best_posts),
        posts_read_summary=_format_posts_read(posts_read),
        depth=int(agent.get("news_depth") or 1),
    )

    resp = await client.chat(
        [{"role": "user", "content": prompt}],
        model=config.OPENROUTER_COMMUNITY_MODEL,
        temperature=0.3,
    )
    return response_content(resp).strip()


def _format_best_posts(best_posts: list[dict]) -> str:
    if not best_posts:
        return "(어제 Best 게시글 없음)"
    lines = []
    for p in best_posts:
        lines.append(f"- [{p.get('post_type','')}] {p.get('title','')} (score: {p.get('score',0)})")
    return "\n".join(lines)


def _format_posts_read(posts_read: list[dict]) -> str:
    if not posts_read:
        return "(어제 직접 읽은 게시글 없음)"
    lines = []
    for p in posts_read:
        reaction = p.get("reaction", "read")
        badges = ", ".join(p.get("author_badges") or []) or "없음"
        lines.append(
            f"- [{p.get('post_type','')}] {p.get('title','')} | 내 반응: {reaction} | 작성자 뱃지: {badges}\n"
            f"  내용 요약: {str(p.get('content',''))[:200]}"
        )
    return "\n\n".join(lines)
```

---

### 4-4. community/posting.py — 게시글 작성 결정 LLM

```python
# twinmarket_kr/community/posting.py
from __future__ import annotations
import json
from typing import Any

import config
from twinmarket_kr.llm.client import OpenRouterClient, response_content
from twinmarket_kr.llm.belief import load_prompt
from twinmarket_kr.llm.analysis import parse_json_loose


POST_TYPES_GUIDE = """
게시글 타입 6종 (하나를 선택):
- impression  : 짧은 감탄, 단상, 느낌 (1~3문장)
- question    : 다른 투자자에게 의견·정보 질문
- trade_share : 오늘 매수·매도 거래 소개 (반드시 실제 거래를 반영할 필요 없음)
- profit_share: 수익·손실 인증, 수익률 공유
- analysis    : 기술적·뉴스 분석, 시장 전망 (비교적 긴 글)
- column      : 한 편의 칼럼 형식, 긴 호흡의 의견
"""


async def posting_decision(
    agent: dict[str, Any],
    today_belief: dict,
    decision: dict,
    date: str,
    client: OpenRouterClient | None = None,
) -> dict | None:
    """
    거래 결정 직후 호출. 게시글을 올릴지 결정하고, 올린다면 내용을 생성한다.
    반환값: {"will_post": True, "post_type": str, "title": str, "content": str}
           또는 None (포스팅 안 함)
    """
    if client is None:
        client = OpenRouterClient()

    prompt_template = load_prompt("posting_decision")

    trade_summary = (
        f"오늘 거래: {decision.get('action','hold')} "
        f"{decision.get('quantity', 0)}주, "
        f"이유: {decision.get('reason','')[:100]}"
    )

    prompt = prompt_template.format(
        persona_prompt=agent.get("persona_prompt", ""),
        belief_summary=today_belief.get("belief_summary", ""),
        view_change=today_belief.get("view_change", ""),
        trade_summary=trade_summary,
        date=date,
        post_types_guide=POST_TYPES_GUIDE,
    )

    resp = await client.chat(
        [{"role": "user", "content": prompt}],
        model=config.OPENROUTER_COMMUNITY_MODEL,
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    raw = parse_json_loose(response_content(resp))

    if not raw.get("will_post", False):
        return None

    post_type = str(raw.get("post_type", "impression"))
    title = str(raw.get("title", ""))
    content = str(raw.get("content", ""))

    if not title or not content:
        return None

    return {"will_post": True, "post_type": post_type, "title": title, "content": content}
```

---

### 4-5. community/reading.py — 게시글 선택·반응 2단계 LLM

열람 과정을 2번의 LLM 호출로 처리한다.
- **Call 1 (select)**: 게시글 목록 → 읽을 post_id 선택
- **Call 2 (react)**: 선택한 게시글 본문 제공 → 일괄 반응 결정

```python
# twinmarket_kr/community/reading.py
from __future__ import annotations
import json
from typing import Any

import config
from twinmarket_kr.llm.client import OpenRouterClient, response_content
from twinmarket_kr.llm.belief import load_prompt
from twinmarket_kr.llm.analysis import parse_json_loose


async def community_reading_select(
    agent: dict[str, Any],
    post_list: list[dict],
    read_limit: int,
    client: OpenRouterClient | None = None,
) -> list[int]:
    """
    게시글 목록을 보고, 읽고 싶은 게시글 post_id를 최대 read_limit개 선택한다.
    반환값: [post_id, ...]
    """
    if client is None:
        client = OpenRouterClient()
    if not post_list:
        return []

    prompt_template = load_prompt("community_reading")
    post_list_str = _format_post_list(post_list)

    prompt = prompt_template.format(
        mode="select",
        persona_prompt=agent.get("persona_prompt", ""),
        post_list_str=post_list_str,
        read_limit=read_limit,
        posts_content_str="",  # select 단계에서는 사용 안 함
    )

    resp = await client.chat(
        [{"role": "user", "content": prompt}],
        model=config.OPENROUTER_COMMUNITY_MODEL,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    raw = parse_json_loose(response_content(resp))
    selected = [int(pid) for pid in raw.get("selected_post_ids", [])[:read_limit]]
    return selected


async def community_reading_react(
    agent: dict[str, Any],
    posts_content: list[dict],
    client: OpenRouterClient | None = None,
) -> list[dict]:
    """
    선택한 게시글의 본문(+ Depth 2는 작성자 프로필 포함)을 받아 일괄 반응을 결정한다.
    반환값: [{"post_id": int, "reaction": "like"|"unlike"|"none"}, ...]
    """
    if client is None:
        client = OpenRouterClient()
    if not posts_content:
        return []

    prompt_template = load_prompt("community_reading")
    posts_content_str = _format_posts_content(posts_content)

    prompt = prompt_template.format(
        mode="react",
        persona_prompt=agent.get("persona_prompt", ""),
        post_list_str="",  # react 단계에서는 사용 안 함
        read_limit=len(posts_content),
        posts_content_str=posts_content_str,
    )

    resp = await client.chat(
        [{"role": "user", "content": prompt}],
        model=config.OPENROUTER_COMMUNITY_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = parse_json_loose(response_content(resp))
    reactions = raw.get("reactions", [])
    validated = []
    for r in reactions:
        pid = r.get("post_id")
        reaction = r.get("reaction", "none")
        if pid is not None and reaction in ("like", "unlike", "none"):
            validated.append({"post_id": int(pid), "reaction": reaction})
    return validated


def _format_post_list(post_list: list[dict]) -> str:
    lines = []
    for p in post_list:
        badges_str = ", ".join(p.get("author_badges") or []) or "없음"
        lines.append(
            f"[post_id={p['post_id']}] [{p.get('post_type','')}] {p.get('title','')} "
            f"| 작성자: {p.get('anonymous_code','')} [{badges_str}] "
            f"| 👍{p.get('like_count',0)} 👎{p.get('unlike_count',0)}"
        )
    return "\n".join(lines)


def _format_posts_content(posts_content: list[dict]) -> str:
    parts = []
    for p in posts_content:
        profile_str = ""
        if p.get("author_profile"):
            profile = p["author_profile"]
            profile_str = f"\n[작성자 실적] {json.dumps(profile.get('portfolio_summary', {}), ensure_ascii=False)[:300]}"
        parts.append(
            f"--- post_id={p['post_id']} [{p.get('post_type','')}] ---\n"
            f"제목: {p.get('title','')}\n"
            f"본문: {p.get('content','')}"
            f"{profile_str}"
        )
    return "\n\n".join(parts)
```

---

## 5. Step 4 — 프롬프트 파일 3개 작성

### 5-1. prompts/community_thinking.txt

아래 내용과 구조로 작성한다.

```
당신은 삼성전자(005930)에 투자하는 개인 투자자입니다.

[페르소나]
{persona_prompt}

[어제 커뮤니티 Best 게시글]
{best_posts_summary}

[어제 내가 직접 읽은 게시글과 내 반응]
{posts_read_summary}

위 커뮤니티 경험을 바탕으로, 오늘 투자 판단에 영향을 줄 수 있는 생각을 정리해 주세요.

다음 관점에서 자유롭게 서술하세요 (200~400자):
1. 어제 커뮤니티에서 느낀 전반적인 분위기 (낙관적/비관적/혼조)
2. 특히 인상 깊었던 의견이나 정보 — 내 기존 생각을 강화하거나 흔들었는가?
3. 오늘 투자 판단에 반영할 점

자유 형식 텍스트로 작성하세요. JSON이 아닙니다.
```

**입력 변수**: `{persona_prompt}`, `{best_posts_summary}`, `{posts_read_summary}`, `{depth}`

---

### 5-2. prompts/posting_decision.txt

```
당신은 삼성전자(005930)에 투자하는 개인 투자자입니다. 오늘 장이 끝난 직후입니다.

[페르소나]
{persona_prompt}

[오늘의 투자 관점 요약]
{belief_summary}

[관점 변화]
{view_change}

[오늘 거래 내역 참고]
{trade_summary}

[날짜]
{date}

{post_types_guide}

커뮤니티(종목토론방)에 글을 올릴지 결정하고, 올린다면 내용을 작성해 주세요.

주의:
- 반드시 올릴 필요는 없습니다. 올리고 싶을 때만 올리세요.
- 거래 내역을 그대로 공개할 필요 없습니다. 자유롭게 표현하세요.
- 페르소나에 충실하게, 자연스럽게 작성하세요.

JSON으로 응답하세요:
{{
  "will_post": true 또는 false,
  "post_type": "타입명 (will_post=false면 생략)",
  "title": "제목 (will_post=false면 생략)",
  "content": "본문 내용 (will_post=false면 생략)"
}}
```

**입력 변수**: `{persona_prompt}`, `{belief_summary}`, `{view_change}`, `{trade_summary}`, `{date}`, `{post_types_guide}`

---

### 5-3. prompts/community_reading.txt (mode 파라미터 방식)

`news_agent.txt`처럼 `{mode}` 값에 따라 분기하는 단일 파일로 작성한다.

```
당신은 삼성전자(005930)에 투자하는 개인 투자자입니다.

[페르소나]
{persona_prompt}

[모드: {mode}]

---

### select 모드 (글 목록 보기)

오늘 커뮤니티에 올라온 게시글 목록입니다:

{post_list_str}

페르소나와 현재 관심사에 따라 읽고 싶은 글을 최대 {read_limit}개 선택하세요.

JSON으로 응답:
{{
  "selected_post_ids": [post_id, ...]
}}

---

### react 모드 (글 읽고 반응)

선택한 게시글의 본문입니다:

{posts_content_str}

각 글을 읽고 반응을 결정하세요.
- like  : 이 글의 내용에 공감하거나 도움이 됨
- unlike: 이 글의 내용에 동의하지 않거나 불쾌함
- none  : 읽었지만 특별한 반응 없음

JSON으로 응답:
{{
  "reactions": [
    {{"post_id": int, "reaction": "like"|"unlike"|"none"}},
    ...
  ]
}}
```

**입력 변수**: `{mode}`, `{persona_prompt}`, `{post_list_str}`, `{read_limit}`, `{posts_content_str}`

---

## 6. Step 5 — collect_context.py 수정

**파일**: `twinmarket_kr/core/collect_context.py`

`collect_context()` 함수 시그니처에 `community_agent` 파라미터를 추가하고, community_log를 수집한다.

### 변경 전 시그니처
```python
def collect_context(
    agent,
    *,
    turn: int,
    date: str,
    memory_agent: MemoryAgent,
    fundamental_agent: FundamentalAgent,
    news_agent: NewsAgent,
) -> dict:
```

### 변경 후 시그니처
```python
def collect_context(
    agent,
    *,
    turn: int,
    date: str,
    memory_agent: MemoryAgent,
    fundamental_agent: FundamentalAgent,
    news_agent: NewsAgent,
    community_agent=None,  # CommunityAgent | None — 타입은 순환 import 방지를 위해 생략 가능
) -> dict:
```

### 함수 본문 끝에 추가

```python
# Community log 수집 (turn 1은 전날 로그 없음)
community_log = None
if (
    community_agent is not None
    and turn > 1
    and int(agent.get("news_depth") or 0) >= 1
):
    community_log = community_agent.get_community_log(agent["agent_id"], turn - 1)

context["community_log"] = community_log
```

반환 dict에 `"community_log"` 키가 추가된다.

---

## 7. Step 6 — daily_cycle.py 수정

**파일**: `twinmarket_kr/core/daily_cycle.py`

전체 변경 사항을 단계별로 설명한다.

### 7-1. import 추가

파일 상단에 아래 import를 추가한다.

```python
import asyncio
import config
from twinmarket_kr.community.thinking import community_thinking
from twinmarket_kr.community.posting import posting_decision
```

(이미 `import config`가 있으면 생략)

### 7-2. run_agent_turn() 시그니처 변경

```python
async def run_agent_turn(
    agent: dict[str, Any],
    *,
    turn: int,
    date: str,
    memory_agent: MemoryAgent,
    fundamental_agent: FundamentalAgent,
    news_agent: NewsAgent,
    client: OpenRouterClient | None = None,
    event_logger: Any | None = None,
    community_agent=None,  # CommunityAgent | None
) -> dict[str, Any] | None:
```

### 7-3. collect_context() 호출 수정

```python
today_context = collect_context(
    agent,
    turn=turn,
    date=date,
    memory_agent=memory_agent,
    fundamental_agent=fundamental_agent,
    news_agent=news_agent,
    community_agent=community_agent,          # 추가
)
```

### 7-4. community_thinking 단계 추가 (interpret_news와 병렬 실행)

현재 코드에서 `interpret_news()`를 단독 await하는 부분을:

```python
# 기존
news_interpretation = await interpret_news(agent, today_context["news_context"], client=client)
```

아래와 같이 병렬 처리로 변경한다.

```python
depth = int(agent.get("news_depth") or 0)
community_log = today_context.get("community_log")

# News Thinking + Community Thinking 병렬 실행
should_do_community_thinking = (
    config.ENABLE_COMMUNITY
    and depth >= 1
    and community_log is not None
)

if should_do_community_thinking:
    news_interpretation, community_thinking_text = await asyncio.gather(
        interpret_news(agent, today_context["news_context"], client=client),
        community_thinking(agent, community_log, client=client),
    )
else:
    news_interpretation = await interpret_news(agent, today_context["news_context"], client=client)
    community_thinking_text = None

today_context["news_interpretation"] = news_interpretation
today_context["community_thinking"] = community_thinking_text
```

### 7-5. update_belief() 호출 — 변경 없음

`update_belief()`는 `today_context` 전체를 받으므로 별도 수정이 필요 없다.  
다만 `prompts/update_belief.txt`를 수정해야 한다 (Step 8 참조).

### 7-6. posting_decision 단계 추가 (make_decision 직후)

```python
# make_decision 직후, order 생성 전
decision = await make_decision(...)

# ─ Community Posting ─
if (
    config.ENABLE_COMMUNITY
    and config.ENABLE_COMMUNITY_POSTING
    and depth >= 1
    and community_agent is not None
):
    post_result = await posting_decision(
        agent,
        today_belief=today_belief,
        decision=decision,
        date=date,
        client=client,
    )
    if post_result is not None:
        community_agent.save_post(
            agent_id=str(agent["agent_id"]),
            turn=turn,
            date=date,
            post_type=post_result["post_type"],
            title=post_result["title"],
            content=post_result["content"],
        )
```

### 7-7. event_logger 업데이트 (선택)

`event_logger.log_agent_turn()`에 `community_thinking=community_thinking_text`를 추가할 수 있다.  
기존 로거 인터페이스와 충돌 시 생략해도 된다.

---

## 8. Step 7 — simulation.py 수정

**파일**: `twinmarket_kr/simulation.py`

### 8-1. import 추가

```python
from twinmarket_kr.community.agent import CommunityAgent
from twinmarket_kr.community.badge import calculate_badges
from twinmarket_kr.community.reading import community_reading_select, community_reading_react
```

### 8-2. run_simulation() — CommunityAgent 초기화

기존 `exchange = ExchangeAgent(...)` 줄 아래에:

```python
community = CommunityAgent(config.SIM_DB) if config.ENABLE_COMMUNITY else None
```

### 8-3. guarded_turn() — community_agent 파라미터 전달

```python
async def guarded_turn(agent, turn, day):
    async with semaphore:
        try:
            return await run_agent_turn(
                agent,
                turn=turn,
                date=day,
                memory_agent=memory,
                fundamental_agent=fundamental,
                news_agent=news,
                client=client,
                event_logger=logger,
                community_agent=community,     # 추가
            )
        except Exception as exc:
            ...
```

### 8-4. 하루 루프 끝에 community_phase() 호출

`_update_portfolios_from_results(...)` 호출 직후:

```python
_update_portfolios_from_results(...)

if config.ENABLE_COMMUNITY and community is not None:
    await community_phase(
        agents=agents,
        community_agent=community,
        memory_agent=memory,
        turn=index,
        date=day,
        client=client,
    )
```

### 8-5. community_phase() 함수 구현

`run_simulation()` 외부에 아래 함수를 추가한다.

```python
async def community_phase(
    *,
    agents: list[dict[str, Any]],
    community_agent: CommunityAgent,
    memory_agent: MemoryAgent,
    turn: int,
    date: str,
    client: OpenRouterClient,
) -> None:
    """
    하루가 끝난 후 Depth 1/2 Agent들이 오늘 올라온 게시글을 열람하고 반응한다.
    Live 방식: 각 Agent의 반응이 완료되는 즉시 DB에 반영되어 다음 Agent가 갱신된 수치를 본다.
    """
    if not config.ENABLE_COMMUNITY_READING:
        return

    # 뱃지 계산 (LLM 없음)
    badges = calculate_badges(agents, memory_agent, turn, config.SIM_DB)

    # Depth 1/2 Agent만 선별
    active_agents = [
        a for a in agents if int(a.get("news_depth") or 0) >= 1
    ]
    if not active_agents:
        return

    # Best 게시글 목록 (community_log에 넣을 용도)
    # — 아직 is_best 마킹 전이지만, 오늘자 score 기준 상위를 미리 조회
    # — mark_best_posts는 모든 반응이 끝난 후 호출하므로 여기서는 post_list만 사용

    semaphore = asyncio.Semaphore(8)  # 기존과 동일한 동시성 제한

    async def _one_agent_reading(agent: dict[str, Any]) -> tuple[str, list[dict], list[dict]]:
        async with semaphore:
            depth = int(agent.get("news_depth") or 0)
            read_limit = (
                config.COMMUNITY_DEPTH2_READ_LIMIT
                if depth >= 2
                else config.COMMUNITY_DEPTH1_READ_LIMIT
            )
            agent_id = str(agent["agent_id"])

            # 현재 시점 게시글 목록 (Live: 다른 Agent 반응이 반영된 최신 수치)
            post_list = community_agent.get_today_posts(date)
            if not post_list:
                return agent_id, [], []

            # 뱃지 정보 추가
            post_list_with_badges = [
                {**p, "author_badges": badges.get(str(p["agent_id"]), [])}
                for p in post_list
            ]

            # Call 1: 게시글 선택
            selected_ids = await community_reading_select(
                agent, post_list_with_badges, read_limit, client=client
            )
            if not selected_ids:
                return agent_id, [], []

            # 선택된 게시글 본문 수집
            posts_content = []
            for pid in selected_ids:
                content = community_agent.get_post_content(pid)
                if not content:
                    continue
                # Depth 2: 작성자 프로필 자동 첨부
                if depth >= 2:
                    content["author_profile"] = community_agent.get_author_profile(
                        content["agent_id"], memory_agent, turn
                    )
                else:
                    content["author_profile"] = None
                posts_content.append(content)

            # Call 2: 일괄 반응 결정
            reactions = await community_reading_react(agent, posts_content, client=client)

            # 반응 기록 + Live 점수 갱신
            reaction_map = {r["post_id"]: r["reaction"] for r in reactions}
            for pc in posts_content:
                pid = pc["post_id"]
                reaction = reaction_map.get(pid, "read")
                community_agent.record_reaction(agent_id, pid, turn, date, reaction)
                if reaction in ("like", "unlike"):
                    community_agent.update_post_score_live(pid, reaction)

            # posts_read 구성 (community_log에 저장)
            posts_read = []
            for pc in posts_content:
                pid = pc["post_id"]
                posts_read.append(
                    {
                        "post_id": pid,
                        "title": pc.get("title", ""),
                        "post_type": pc.get("post_type", ""),
                        "content": pc.get("content", ""),
                        "reaction": reaction_map.get(pid, "read"),
                        "author_badges": badges.get(str(pc.get("agent_id", "")), []),
                        "author_profile": pc.get("author_profile"),
                    }
                )
            return agent_id, post_list_with_badges, posts_read

    # 모든 Depth 1/2 Agent 병렬 실행 (Live 방식 — 먼저 완료된 Agent 반응이 즉시 DB 반영)
    results = await asyncio.gather(*(_one_agent_reading(a) for a in active_agents))

    # Best 게시글 선정 (모든 반응 완료 후)
    best_posts = community_agent.mark_best_posts(date, config.COMMUNITY_BEST_POST_COUNT)

    # Community Log 저장
    for agent_id, post_list_with_badges, posts_read in results:
        community_agent.save_community_log(
            agent_id=agent_id,
            turn=turn,
            date=date,
            best_posts=best_posts,
            posts_read=posts_read,
            thinking="",  # Community Thinking은 다음날 아침 daily_cycle에서 생성
        )

    print(f"  community_phase done: {len(active_agents)} agents, {len(best_posts)} best posts")
```

**참고**: `community_thinking`은 community_phase에서 생성하지 않는다. 다음날 아침 `run_agent_turn()` 내에서 `community_thinking()`이 호출된다. `community_logs` 테이블에 `thinking`은 일단 빈 문자열로 저장하며, 다음날 daily_cycle에서 `save_community_log`를 다시 호출하거나 별도 UPDATE 쿼리로 채울 수 있다.

**대안**: thinking을 community_phase 종료 후 곧바로 생성해 저장하는 방식도 가능하다. 단, 이 경우 community_phase 안에서 LLM 호출이 한 번 더 추가된다.  
→ **권장**: thinking은 다음날 아침 `run_agent_turn()`에서 생성 (Community Thinking 텍스트가 당일 Belief 업데이트 직전에 fresh하게 만들어지는 것이 더 자연스럽다).

---

## 9. Step 8 — update_belief.txt 수정

**파일**: `prompts/update_belief.txt`

현재 `update_belief.txt`는 `{today_context}` 변수(또는 개별 변수들)를 받는다.  
Community Thinking을 Belief 업데이트에 반영하려면, 프롬프트에 조건부로 community_thinking 섹션을 추가한다.

### 추가할 내용

기존 뉴스 해석 섹션 다음에 아래를 삽입한다.

```
[커뮤니티 경험 (오늘 아침 반영)]
{community_thinking}
(없으면 비어 있음 — 무시하세요)
```

`update_belief()`를 호출하기 전에 `today_context["community_thinking"]`이 설정되어 있으면 자동으로 전달된다.  
`today_context`를 프롬프트에 통째로 직렬화하는 방식이라면 자동으로 포함된다.  
개별 변수로 주입하는 방식이라면 `belief.py`의 `update_belief()` 내 `format()` 호출에 `community_thinking=today_context.get("community_thinking") or ""` 를 추가한다.

**기존 `belief.py::update_belief()` 확인 후**: 프롬프트에 어떤 변수가 쓰이는지 확인하고, `{community_thinking}`이 없으면 추가한다.

---

## 10. 구현 순서 권장

아래 순서로 구현하면 각 Step이 이전 Step에 의존하지 않거나 최소한의 의존성만 갖는다.

| 순서 | Step | 의존성 |
|------|------|--------|
| 1 | DB 스키마 추가 (`schema.py`) | 없음 |
| 2 | `config.py` 설정 추가 | 없음 |
| 3 | `community/badge.py` | `config.py` |
| 4 | `community/agent.py` — CommunityAgent | DB 스키마, `config.py` |
| 5 | 프롬프트 3개 작성 (`*.txt`) | 없음 |
| 6 | `community/thinking.py` | 프롬프트, `community/agent.py` |
| 7 | `community/posting.py` | 프롬프트 |
| 8 | `community/reading.py` | 프롬프트 |
| 9 | `collect_context.py` 수정 | `community/agent.py` |
| 10 | `daily_cycle.py` 수정 | 위 모든 것 |
| 11 | `simulation.py` 수정 | 위 모든 것 |
| 12 | `update_belief.txt` 수정 | 없음 |

---

## 11. 검증 방법

### 최소 검증 (단위)

```python
# 1. CommunityAgent 기본 동작
ca = CommunityAgent(config.SIM_DB)
post_id = ca.save_post("agent_1", 1, "2024-01-02", "impression", "테스트 제목", "테스트 본문")
posts = ca.get_today_posts("2024-01-02")
assert len(posts) == 1

# 2. 뱃지 계산 (에러 없이 실행되는지)
badges = calculate_badges(agents[:3], memory, turn=1, db_path=config.SIM_DB)
assert isinstance(badges, dict)

# 3. 익명 코드 결정론성
code1 = ca.generate_anonymous_code("agent_001")
code2 = ca.generate_anonymous_code("agent_001")
assert code1 == code2
```

### 통합 검증

```bash
# max_agents=3, max_days=2로 짧게 돌려 전체 흐름 확인
python -c "
import asyncio
from twinmarket_kr.simulation import run_simulation
asyncio.run(run_simulation(max_agents=3, max_days=2))
"
```

통합 실행 후 확인할 사항:
- `community_posts` 테이블에 게시글이 쌓이는가
- `community_interactions` 테이블에 반응이 기록되는가
- `community_logs` 테이블에 각 Agent의 로그가 저장되는가
- `belief_history`의 day 2 이후 Belief가 community_thinking을 반영하는가 (로그에서 확인)
- `config.ENABLE_COMMUNITY = False`로 설정 시 기존과 동일하게 동작하는가

---

## 12. 주의사항 및 엣지 케이스

1. **Turn 1 (첫날)**: `community_log`가 없으므로 `community_thinking` 스킵. Depth 0/1/2 구분 없이 posting만 가능.
2. **포스팅이 0건인 날**: `community_phase()`에서 `get_today_posts()` 결과가 빈 리스트 → 읽기 단계 스킵, Best 게시글 0건.
3. **Depth 0 Agent**: `run_agent_turn()`에서 `depth >= 1` 조건에 걸려 community_thinking, posting 모두 스킵.
4. **DB 동시 쓰기**: `asyncio.gather()`로 병렬 실행 시 SQLite write lock 충돌 가능. `connect()`에 `check_same_thread=False`와 WAL 모드(`PRAGMA journal_mode=WAL`)를 적용한다. 기존 `connection.py`에 이미 적용되어 있으면 그대로 사용.
5. **MemoryAgent.get_recent_trades()**: 이 메서드가 없을 경우 `CommunityAgent.get_author_profile()` 안에서 직접 `trade_log` 테이블을 쿼리하는 코드를 작성한다.
6. **프롬프트 format() 에러**: `today_context`를 `json.dumps()` 후 프롬프트에 넣는 방식이라면 `community_thinking` 키가 없을 때 `KeyError` 발생 가능 → `.get("community_thinking") or ""`로 방어.

---

## 진행 로그

| Step | 상태 | 완료 일시 | 메모 |
|------|------|-----------|------|
| 1. DB 스키마 | 미완료 | — | — |
| 2. config.py | 미완료 | — | — |
| 3. community/badge.py | 미완료 | — | — |
| 4. community/agent.py | 미완료 | — | — |
| 5. 프롬프트 3개 | 미완료 | — | — |
| 6. community/thinking.py | 미완료 | — | — |
| 7. community/posting.py | 미완료 | — | — |
| 8. community/reading.py | 미완료 | — | — |
| 9. collect_context.py | 미완료 | — | — |
| 10. daily_cycle.py | 미완료 | — | — |
| 11. simulation.py | 미완료 | — | — |
| 12. update_belief.txt | 미완료 | — | — |
