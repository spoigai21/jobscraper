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
    poll_interval_business: int = 2700
    poll_interval_overnight: int = 10800
    business_hours_start: int = 9
    business_hours_end: int = 19
    request_timeout: int = 15
    min_alert_interval: int = 3600
    user_agent: str = DEFAULT_USER_AGENT
    monitor_db_path: str = str(DEFAULT_DB_PATH)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        twilio_from_number=os.getenv("TWILIO_FROM_NUMBER", ""),
        twilio_to_number=os.getenv("TWILIO_TO_NUMBER", ""),
        ntfy_topic=os.getenv("NTFY_TOPIC", ""),
        ntfy_token=os.getenv("NTFY_TOKEN", ""),
        alert_email_to=os.getenv("ALERT_EMAIL_TO", ""),
        poll_interval_business=_env_int("POLL_INTERVAL_BUSINESS", 2700),
        poll_interval_overnight=_env_int("POLL_INTERVAL_OVERNIGHT", 10800),
        business_hours_start=_env_int("BUSINESS_HOURS_START", 9),
        business_hours_end=_env_int("BUSINESS_HOURS_END", 19),
        request_timeout=_env_int("REQUEST_TIMEOUT", 15),
        min_alert_interval=_env_int("MIN_ALERT_INTERVAL", 3600),
        user_agent=os.getenv("USER_AGENT") or DEFAULT_USER_AGENT,
        monitor_db_path=os.getenv("MONITOR_DB_PATH") or str(DEFAULT_DB_PATH),
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
