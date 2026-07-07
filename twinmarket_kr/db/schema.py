from __future__ import annotations


AGENTS_DDL = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    source_user_id TEXT NOT NULL,
    user_type TEXT NOT NULL,
    gender TEXT NOT NULL,
    age INTEGER NOT NULL,
    age_group TEXT NOT NULL,
    location TEXT NOT NULL,
    bh_disposition_effect_category TEXT NOT NULL,
    bh_lottery_preference_category TEXT NOT NULL,
    bh_total_return_category TEXT NOT NULL,
    bh_underdiversification_category TEXT NOT NULL,
    strategy TEXT NOT NULL,
    trad_pro INTEGER NOT NULL DEFAULT 0,
    fol_ind TEXT NOT NULL,
    ini_cash INTEGER NOT NULL,
    news_depth INTEGER NOT NULL DEFAULT 1,
    segment_key TEXT NOT NULL,
    match_score INTEGER NOT NULL,
    persona_prompt TEXT NOT NULL
);
"""

SIM_DDLS = [
    """
    CREATE TABLE IF NOT EXISTS belief_history (
        belief_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        turn INTEGER NOT NULL,
        date TEXT NOT NULL,
        dim_1 TEXT,
        dim_2 TEXT,
        dim_3 TEXT,
        dim_4 TEXT,
        dim_5 TEXT,
        dim_6 TEXT,
        belief_summary TEXT NOT NULL,
        view_change TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_state (
        state_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        turn INTEGER NOT NULL,
        date TEXT NOT NULL,
        cash REAL NOT NULL,
        positions TEXT NOT NULL,
        total_value REAL NOT NULL,
        realized_pnl REAL NOT NULL,
        total_return_rate REAL NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_log (
        log_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        turn INTEGER NOT NULL,
        date TEXT NOT NULL,
        action TEXT NOT NULL,
        stock_code TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        executed_price REAL,
        trade_value REAL,
        fee REAL NOT NULL,
        action_reason TEXT,
        risk_control TEXT,
        order_type TEXT,
        submitted_price REAL,
        status TEXT NOT NULL DEFAULT 'pending',
        filled_quantity INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_system_messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        turn INTEGER NOT NULL,
        date TEXT NOT NULL,
        message_type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS StockData (
        date TEXT NOT NULL,
        stock_id TEXT NOT NULL,
        open_price REAL,
        high_price REAL,
        low_price REAL,
        close_price REAL NOT NULL,
        volume REAL,
        pct_chg REAL,
        volume_chg REAL,
        ma5 REAL,
        ma20 REAL,
        volatility_20d REAL,
        PRIMARY KEY (date, stock_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS TradingDetails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        stock_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        trading_direction TEXT NOT NULL,
        price REAL NOT NULL,
        volume INTEGER NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS community_posts (
        post_id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        anonymous_code TEXT NOT NULL,
        turn INTEGER NOT NULL,
        date TEXT NOT NULL,
        post_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        like_count INTEGER NOT NULL DEFAULT 0,
        unlike_count INTEGER NOT NULL DEFAULT 0,
        score INTEGER NOT NULL DEFAULT 0,
        is_best INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS community_interactions (
        interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        post_id INTEGER NOT NULL,
        turn INTEGER NOT NULL,
        date TEXT NOT NULL,
        reaction TEXT NOT NULL,
        UNIQUE(agent_id, post_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS community_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        turn INTEGER NOT NULL,
        date TEXT NOT NULL,
        best_posts_seen TEXT,
        posts_read TEXT,
        community_thinking TEXT,
        UNIQUE(agent_id, turn)
    );
    """,
]


def create_agents_table_sql() -> str:
    return AGENTS_DDL


def create_sim_tables_sql() -> list[str]:
    return SIM_DDLS
