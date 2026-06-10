from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs) -> bool:  # type: ignore[no-redef]
        return False


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
PROMPT_DIR = PROJECT_ROOT / "prompts"
LOG_DIR = OUTPUT_DIR / "logs"

SYS_1000_DB = DATA_DIR / "sys_1000.db"
SYS_1000_CSV = DATA_DIR / "sys_1000.csv"
FIXED_SLOTS_CSV = DATA_DIR / "fixed_slots.csv"
STOCK_DATA_CSV = DATA_DIR / "stock_data.csv"
TRADING_DAYS_CSV = DATA_DIR / "trading_days.csv"
SAMSUNG_NEWS_RAW_PKL = DATA_DIR / "samsung_news_raw.pkl"
PROCESSED_NEWS_CSV = OUTPUT_DIR / "processed_news.csv"
DAILY_NEWS_SELECTION_CSV = OUTPUT_DIR / "daily_news_selection.csv"
SYS_100_DB = OUTPUT_DIR / "sys_100.db"
SIM_DB = OUTPUT_DIR / "sim.db"

STOCK_CODE = "005930"
COMMISSION_RATE = 0.00015
CIRCUIT_BREAKER = 0.30
N_WARMUP = 3
N_TRANSITION = 4
INI_CASH_SMALL = 100_000_000
INI_CASH_LARGE = 1_000_000_000
MIN_ORDER_UNIT = 1
RANDOM_SEED = 2
NEWS_DEPTH2_RATIO = 0.30
NEWS_DEPTH0_COUNT = 15
MAX_SINGLE_TRADE_CASH_RATIO = 0.50

BELIEF_LIMITS = {
    "dim_1": 150,
    "dim_2": 100,
    "dim_3": 100,
    "dim_4": 100,
    "dim_5": 100,
    "dim_6": 100,
}

EXPERIMENT_START_DATE = ""
EXPERIMENT_END_DATE = ""

load_dotenv(PROJECT_ROOT / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
OPENROUTER_EMBED_MODEL = os.getenv("OPENROUTER_EMBED_MODEL", "")


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
