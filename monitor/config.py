from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
LOG_FILE = PROJECT_ROOT / "monitor.log"
DEFAULT_DB_PATH = PROJECT_ROOT / "monitor.db"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Polite delay between paginated API/page fetches.
PAGE_FETCH_DELAY_SECONDS = 0.5

# Eightfold PCSX/apply v2 boards (Microsoft, Netflix, etc.) are rate-sensitive.
EIGHTFOLD_PAGE_DELAY_SECONDS = 2.0
EIGHTFOLD_MAX_PAGES = 5

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


@dataclass(frozen=True, slots=True)
class Settings:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    twilio_to_number: str
    ntfy_topic: str
    alert_email_to: str
    ntfy_token: str = ""
    discord_webhook_url: str = ""
    poll_interval_business: int = 2700
    poll_interval_overnight: int = 10800
    business_hours_start: int = 9
    business_hours_end: int = 19
    request_timeout: int = 15
    min_alert_interval: int = 3600
    max_alerts_per_company_per_cycle: int = 0  # 0 = unlimited (no per-cycle cap)
    # Suppress a repeat alert for the same employer+role within this many days
    # (re-posts get fresh job IDs). 0 = disabled.
    alert_dedup_window_days: int = 30
    # Skip a listing seen for the first time if the source says it was posted
    # more than this many days ago (stale backfill). Only applies to sources
    # that report a publish date. 0 = disabled.
    max_new_listing_age_days: int = 14
    user_agent: str = DEFAULT_USER_AGENT
    monitor_db_path: str = str(DEFAULT_DB_PATH)
    health_ping_enabled: bool = True
    health_ping_interval_seconds: int = 86400
    poll_workers: int = 1
    poll_domain_max_concurrent: int = 2


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        twilio_from_number=os.getenv("TWILIO_FROM_NUMBER", ""),
        twilio_to_number=os.getenv("TWILIO_TO_NUMBER", ""),
        ntfy_topic=os.getenv("NTFY_TOPIC", ""),
        ntfy_token=os.getenv("NTFY_TOKEN", ""),
        discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
        alert_email_to=os.getenv("ALERT_EMAIL_TO", ""),
        poll_interval_business=_env_int("POLL_INTERVAL_BUSINESS", 2700),
        poll_interval_overnight=_env_int("POLL_INTERVAL_OVERNIGHT", 10800),
        business_hours_start=_env_int("BUSINESS_HOURS_START", 9),
        business_hours_end=_env_int("BUSINESS_HOURS_END", 19),
        request_timeout=_env_int("REQUEST_TIMEOUT", 15),
        min_alert_interval=_env_int("MIN_ALERT_INTERVAL", 3600),
        max_alerts_per_company_per_cycle=_env_int(
            "MAX_ALERTS_PER_COMPANY_PER_CYCLE", 0
        ),
        alert_dedup_window_days=_env_int("ALERT_DEDUP_WINDOW_DAYS", 30),
        max_new_listing_age_days=_env_int("MAX_NEW_LISTING_AGE_DAYS", 14),
        user_agent=os.getenv("USER_AGENT") or DEFAULT_USER_AGENT,
        monitor_db_path=os.getenv("MONITOR_DB_PATH") or str(DEFAULT_DB_PATH),
        health_ping_enabled=_env_bool("HEALTH_PING_ENABLED", True),
        health_ping_interval_seconds=_env_int("HEALTH_PING_INTERVAL_SECONDS", 86400),
        poll_workers=_env_int("POLL_WORKERS", 1),
        poll_domain_max_concurrent=_env_int("POLL_DOMAIN_MAX_CONCURRENT", 2),
    )


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Twilio's HTTP client logs full request URLs including the account SID.
    logging.getLogger("twilio.http_client").setLevel(logging.WARNING)
