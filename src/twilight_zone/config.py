from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Config:
    db_path: Path
    log_level: str
    llm_provider: str
    openai_api_key: str
    openai_model: str
    gemini_api_key: str
    gemini_model: str
    search_endpoint: str
    search_api_key: str
    search_provider: str
    telegram_bot_token: str
    telegram_user_id: str
    telegram_dry_run: bool
    analysis_interval_minutes: int
    search_interval_minutes: int
    delivery_interval_minutes: int
    self_review_interval_hours: int

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        return cls(
            db_path=Path(os.getenv("TZ_DB_PATH", "./data/twilight_zone.sqlite3")),
            log_level=os.getenv("TZ_LOG_LEVEL", "INFO"),
            llm_provider=os.getenv("TZ_LLM_PROVIDER", "null").strip().lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            search_endpoint=os.getenv("TZ_SEARCH_ENDPOINT", ""),
            search_api_key=os.getenv("TZ_SEARCH_API_KEY", ""),
            search_provider=os.getenv("TZ_SEARCH_PROVIDER", "bing").strip().lower(),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_user_id=os.getenv("TELEGRAM_USER_ID", ""),
            telegram_dry_run=_bool_env("TZ_TELEGRAM_DRY_RUN", True),
            analysis_interval_minutes=_int_env("TZ_ANALYSIS_INTERVAL_MINUTES", 180),
            search_interval_minutes=_int_env("TZ_SEARCH_INTERVAL_MINUTES", 90),
            delivery_interval_minutes=_int_env("TZ_DELIVERY_INTERVAL_MINUTES", 20),
            self_review_interval_hours=_int_env("TZ_SELF_REVIEW_INTERVAL_HOURS", 72),
        )
