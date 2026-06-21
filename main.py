from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import schedule

from alerts import AlertManager
from companies import COMPANIES
from config import Settings, get_settings, setup_logging
from models import CompanyConfig, StateRecord
from profile import UserProfile, load_profile
from scraper import CareerPageScraper
from storage import StateStore

logger = logging.getLogger(__name__)
PACIFIC = ZoneInfo("America/Los_Angeles")


def _load_user_profile() -> UserProfile | None:
    try:
        return load_profile()
    except FileNotFoundError:
        logger.warning("profile.yaml not found; scoring profile unavailable")
        return None
    except ValueError as exc:
        logger.error("Invalid profile.yaml: %s", exc)
        return None


def get_poll_interval(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    hour = datetime.now(PACIFIC).hour
    if settings.business_hours_start <= hour < settings.business_hours_end:
        return settings.poll_interval_business
    return settings.poll_interval_overnight


def _default_state(company: CompanyConfig) -> StateRecord:
    now_iso = datetime.now(timezone.utc).isoformat()
    return StateRecord(
        company=company.name,
        url=company.url,
        last_hash="",
        last_text="",
        last_checked=now_iso,
        last_alerted=None,
        alert_count=0,
    )


def run_poll_cycle(
    scraper: CareerPageScraper,
    store: StateStore,
    alert_manager: AlertManager,
    companies: list[CompanyConfig],
) -> None:
    enabled = [c for c in companies if c.enabled]
    alerts_fired = 0

    for company in enabled:
        try:
            state = store.get_state(company.name) or _default_state(company)
            payloads = scraper.poll_company(company, state)

            if payloads:
                for payload in payloads:
                    results = alert_manager.fire(payload)
                    store.log_alert(payload, results)
                    alerts_fired += 1
                    label = payload.job_title or payload.trigger_keyword
                    tier_tag = f" [{payload.tier}]" if payload.tier != "standard" else ""
                    print(f"ALERT {company.name} ({label}){tier_tag}")
            else:
                print(f"OK   {company.name}")

            store.upsert_state(state)
        except Exception:
            logger.exception("Poll cycle failed for %s", company.name)
            print(f"ERR  {company.name}")

    print(f"Checked {len(enabled)} companies, {alerts_fired} alerts fired.")


def _poll_and_reschedule(
    scraper: CareerPageScraper,
    store: StateStore,
    alert_manager: AlertManager,
    settings: Settings,
) -> None:
    run_poll_cycle(scraper, store, alert_manager, COMPANIES)
    schedule.clear()
    interval = get_poll_interval(settings)
    schedule.every(interval).seconds.do(
        _poll_and_reschedule, scraper, store, alert_manager, settings
    )
    logger.info("Next poll in %d seconds", interval)


def main() -> None:
    setup_logging()
    settings = get_settings()
    profile = _load_user_profile()
    if profile is not None:
        logger.info(
            "Loaded profile for %s (high tier threshold=%d)",
            profile.user.name,
            profile.alerts.high_score_threshold,
        )
    store = StateStore()
    scraper = CareerPageScraper(settings, profile)
    alert_manager = AlertManager(settings)

    logger.info("Internship monitor starting")
    try:
        _poll_and_reschedule(scraper, store, alert_manager, settings)
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Monitor stopped.")


if __name__ == "__main__":
    main()
