from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import config
from twinmarket_kr.db.connection import connect, init_sim_db


class MemoryAgent:
    def __init__(self, db_path: Path | str = config.SIM_DB) -> None:
        self.db_path = Path(db_path)
        init_sim_db(self.db_path)
        self._ensure_trade_log_columns()

    def save_belief(self, belief: dict[str, Any]) -> None:
        required = {"agent_id", "turn", "date", "belief_summary"}
        missing = required - belief.keys()
        if missing:
            raise ValueError(f"belief missing required keys: {sorted(missing)}")
        belief_id = belief.get("belief_id") or f"belief_{belief['agent_id']}_t{belief['turn']:03d}"
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO belief_history (
                    belief_id, agent_id, turn, date, dim_1, dim_2, dim_3,
                    dim_4, dim_5, dim_6, belief_summary, view_change
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    belief_id,
                    belief["agent_id"],
                    int(belief["turn"]),
                    belief["date"],
                    belief.get("dim_1"),
                    belief.get("dim_2"),
                    belief.get("dim_3"),
                    belief.get("dim_4"),
                    belief.get("dim_5"),
                    belief.get("dim_6"),
                    belief["belief_summary"],
                    belief.get("view_change"),
                ),
            )
            conn.commit()

    def get_previous_belief(self, agent_id: str, turn: int) -> str | None:
        previous_turn = 0 if turn <= 1 else turn - 1
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT belief_summary
                FROM belief_history
                WHERE agent_id = ? AND turn = ?
                """,
                (agent_id, previous_turn),
            ).fetchone()
        return None if row is None else str(row["belief_summary"])

    def init_portfolio_t000(self, agents: list[dict[str, Any]], date: str = "t000") -> None:
        with connect(self.db_path) as conn:
            for agent in agents:
                ini_cash = float(agent["ini_cash"])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO portfolio_state (
                        state_id, agent_id, turn, date, cash, positions,
                        total_value, realized_pnl, total_return_rate
                    ) VALUES (?, ?, 0, ?, ?, ?, ?, 0, 0)
                    """,
                    (
                        f"ps_{agent['agent_id']}_t000",
                        agent["agent_id"],
                        date,
                        ini_cash,
                        "[]",
                        ini_cash,
                    ),
                )
            conn.commit()

    def update_portfolio(
        self,
        agent_id: str,
        turn: int,
        date: str,
        fills: list[dict[str, Any]],
        *,
        current_prices: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        previous = self._latest_portfolio(agent_id, before_or_at_turn=turn - 1)
        if previous is None:
            raise ValueError(f"previous portfolio not found for {agent_id} before turn {turn}")

        cash = float(previous["cash"])
        realized_pnl = float(previous["realized_pnl"])
        initial_value = self._initial_value(agent_id)
        positions = {
            pos["stock_code"]: {
                "stock_code": pos["stock_code"],
                "quantity": int(pos["quantity"]),
                "avg_cost": float(pos["avg_cost"]),
                "current_price": float(pos.get("current_price", pos["avg_cost"])),
                "unrealized_pnl": float(pos.get("unrealized_pnl", 0)),
                "unrealized_pnl_rate": float(pos.get("unrealized_pnl_rate", 0)),
            }
            for pos in json.loads(previous["positions"])
        }

        for fill in fills:
            if fill.get("user_id") not in {None, agent_id}:
                continue
            stock_code = fill.get("stock_code", config.STOCK_CODE)
            direction = fill["direction"]
            quantity = int(fill["quantity"])
            price = float(fill["price"])
            pos = positions.setdefault(
                stock_code,
                {
                    "stock_code": stock_code,
                    "quantity": 0,
                    "avg_cost": 0.0,
                    "current_price": price,
                    "unrealized_pnl": 0.0,
                    "unrealized_pnl_rate": 0.0,
                },
            )
            if direction == "buy":
                total_cost = pos["avg_cost"] * pos["quantity"] + price * quantity
                new_qty = pos["quantity"] + quantity
                pos["quantity"] = new_qty
                pos["avg_cost"] = total_cost / new_qty if new_qty else 0.0
                cash -= price * quantity
            elif direction == "sell":
                sell_qty = min(quantity, pos["quantity"])
                realized_pnl += (price - pos["avg_cost"]) * sell_qty
                pos["quantity"] -= sell_qty
                cash += price * sell_qty
                if pos["quantity"] <= 0:
                    positions.pop(stock_code, None)
            else:
                raise ValueError(f"unknown fill direction: {direction}")

        prices = current_prices or {}
        normalized_positions = []
        stock_value = 0.0
        for stock_code, pos in sorted(positions.items()):
            current_price = float(prices.get(stock_code, pos["current_price"]))
            market_value = pos["quantity"] * current_price
            unrealized = (current_price - pos["avg_cost"]) * pos["quantity"]
            rate = unrealized / (pos["avg_cost"] * pos["quantity"]) if pos["avg_cost"] and pos["quantity"] else 0.0
            pos.update(
                {
                    "current_price": current_price,
                    "unrealized_pnl": unrealized,
                    "unrealized_pnl_rate": rate,
                }
            )
            normalized_positions.append(pos)
            stock_value += market_value

        total_value = cash + stock_value
        total_return_rate = (total_value - initial_value) / initial_value if initial_value else 0.0
        state = {
            "state_id": f"ps_{agent_id}_t{turn:03d}",
            "agent_id": agent_id,
            "turn": turn,
            "date": date,
            "cash": cash,
            "positions": normalized_positions,
            "total_value": total_value,
            "realized_pnl": realized_pnl,
            "total_return_rate": total_return_rate,
        }
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO portfolio_state (
                    state_id, agent_id, turn, date, cash, positions,
                    total_value, realized_pnl, total_return_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state["state_id"],
                    agent_id,
                    turn,
                    date,
                    cash,
                    json.dumps(normalized_positions, ensure_ascii=False),
                    total_value,
                    realized_pnl,
                    total_return_rate,
                ),
            )
            conn.commit()
        return state

    def append_trade_log(self, record: dict[str, Any]) -> None:
        required = {"agent_id", "turn", "date", "action", "stock_code", "quantity"}
        missing = required - record.keys()
        if missing:
            raise ValueError(f"trade log missing required keys: {sorted(missing)}")
        log_id = record.get("log_id") or f"tl_{record['agent_id']}_t{record['turn']:03d}"
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_log (
                    log_id, agent_id, turn, date, action, stock_code, quantity,
                    executed_price, trade_value, fee, action_reason, risk_control,
                    order_type, submitted_price, status, filled_quantity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    record["agent_id"],
                    int(record["turn"]),
                    record["date"],
                    record["action"],
                    record["stock_code"],
                    int(record["quantity"]),
                    record.get("executed_price"),
                    record.get("trade_value"),
                    float(record.get("fee", 0)),
                    record.get("action_reason"),
                    record.get("risk_control"),
                    record.get("order_type"),
                    record.get("submitted_price"),
                    record.get("status", "pending"),
                    int(record.get("filled_quantity", 0)),
                ),
            )
            conn.commit()

    def save_system_message(
        self,
        agent_id: str,
        turn: int,
        date: str,
        *,
        message_type: str,
        message: str,
    ) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO agent_system_messages (
                    agent_id, turn, date, message_type, message
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (agent_id, int(turn), date, message_type, message),
            )
            conn.commit()

    def update_trade_execution(
        self,
        agent_id: str,
        turn: int,
        *,
        filled_quantity: int,
        executed_price: float | None,
        fee: float = 0.0,
    ) -> None:
        log_id = f"tl_{agent_id}_t{turn:03d}"
        status = "filled" if filled_quantity > 0 else "unfilled"
        trade_value = None if executed_price is None else executed_price * filled_quantity
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE trade_log
                SET status = ?,
                    filled_quantity = ?,
                    executed_price = ?,
                    trade_value = ?,
                    fee = ?
                WHERE log_id = ?
                """,
                (status, filled_quantity, executed_price, trade_value, fee, log_id),
            )
            conn.commit()

    def get_recent_order_history(
        self,
        agent_id: str,
        last_n: int = 5,
        *,
        current_date: str | None = None,
    ) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    tl.date,
                    tl.turn,
                    tl.action,
                    tl.status,
                    tl.executed_price,
                    tl.filled_quantity,
                    sd.close_price AS actual_close
                FROM trade_log tl
                LEFT JOIN StockData sd
                  ON sd.date = tl.date AND sd.stock_id = tl.stock_code
                WHERE tl.agent_id = ?
                  AND tl.action IN ('buy', 'sell')
                ORDER BY tl.turn DESC
                LIMIT ?
                """,
                (agent_id, int(last_n)),
            ).fetchall()
        history = []
        for row in rows:
            filled_qty = int(row["filled_quantity"] or 0)
            filled = str(row["status"]) == "filled" and filled_qty > 0
            actual_close = row["actual_close"]
            if current_date is not None and str(row["date"]) >= current_date:
                actual_close = None
            history.append(
                {
                    "date": row["date"],
                    "turn": row["turn"],
                    "action": row["action"],
                    "filled": filled,
                    "status": row["status"],
                    "executed_price": row["executed_price"] if filled else None,
                    "filled_quantity": filled_qty,
                    "actual_close": actual_close,
                }
            )
        return history

    def get_last_action_reason(self, agent_id: str) -> str | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT action, quantity, status, filled_quantity,
                       executed_price, action_reason
                FROM trade_log
                WHERE agent_id = ? AND action IN ('buy', 'sell')
                  AND action_reason IS NOT NULL
                ORDER BY turn DESC
                LIMIT 1
                """,
                (agent_id,),
            ).fetchone()
        if row is None:
            return None
        if row["status"] == "filled":
            result = f"체결 {int(row['filled_quantity']):,}주"
            if row["executed_price"] is not None:
                result += f"@{float(row['executed_price']):,.0f}원"
        elif row["status"] == "unfilled":
            result = "미체결"
        else:
            result = "체결 결과 대기"
        return (
            f"이전 주문: {row['action']} {int(row['quantity']):,}주. "
            f"체결 결과: {result}. 사유: {row['action_reason']}"
        )

    def get_recent_system_message(self, agent_id: str, *, current_turn: int | None = None) -> str | None:
        query = """
            SELECT turn, date, message_type, message
            FROM agent_system_messages
            WHERE agent_id = ?
        """
        params: list[Any] = [agent_id]
        if current_turn is not None:
            query += " AND turn < ?"
            params.append(int(current_turn))
        query += " ORDER BY turn DESC, message_id DESC LIMIT 1"
        with connect(self.db_path) as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            return None
        return f"시스템 알림: {row['date']} turn {row['turn']} {row['message_type']}. {row['message']}"

    def get_portfolio_summary(self, agent_id: str, turn: int) -> str:
        row = self._latest_portfolio(agent_id, before_or_at_turn=turn)
        if row is None:
            raise ValueError(f"portfolio not found for {agent_id} at turn {turn}")
        positions = json.loads(row["positions"])
        cash = float(row["cash"])
        total_value = float(row["total_value"])
        total_return_rate = float(row["total_return_rate"])
        if not positions:
            return (
                f"보유 현금 {cash:,.0f}원, 현재 보유 종목 없음. "
                f"총 자산 {total_value:,.0f}원, 누적 수익률 {total_return_rate * 100:.2f}%."
            )
        parts = []
        for pos in positions:
            parts.append(
                f"{pos['stock_code']} {int(pos['quantity']):,}주 보유, "
                f"평균 매수 단가 {float(pos['avg_cost']):,.0f}원, "
                f"현재가 {float(pos['current_price']):,.0f}원, "
                f"미실현손익 {float(pos['unrealized_pnl']):,.0f}원"
            )
        return (
            f"보유 현금 {cash:,.0f}원, " + "; ".join(parts) + ". "
            f"총 자산 {total_value:,.0f}원, 누적 수익률 {total_return_rate * 100:.2f}%."
        )

    def _latest_portfolio(self, agent_id: str, before_or_at_turn: int) -> sqlite3.Row | None:
        with connect(self.db_path) as conn:
            return conn.execute(
                """
                SELECT *
                FROM portfolio_state
                WHERE agent_id = ? AND turn <= ?
                ORDER BY turn DESC
                LIMIT 1
                """,
                (agent_id, before_or_at_turn),
            ).fetchone()

    def _initial_value(self, agent_id: str) -> float:
        row = self._latest_portfolio(agent_id, before_or_at_turn=0)
        return 0.0 if row is None else float(row["total_value"])

    def _ensure_trade_log_columns(self) -> None:
        expected = {
            "order_type": "TEXT",
            "submitted_price": "REAL",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "filled_quantity": "INTEGER NOT NULL DEFAULT 0",
        }
        with connect(self.db_path) as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(trade_log)").fetchall()}
            for name, ddl in expected.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE trade_log ADD COLUMN {name} {ddl}")
            conn.commit()


def load_agents_from_sys100(sys100_db: Path | str = config.SYS_100_DB) -> list[dict[str, Any]]:
    with connect(sys100_db, read_only=True) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM agents ORDER BY agent_id").fetchall()]
