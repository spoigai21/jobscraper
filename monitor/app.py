from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import schedule

from monitor.alerts import AlertManager
from monitor.companies import COMPANIES
from monitor.config import Settings, get_settings, setup_logging
from monitor.models import CompanyConfig, StateRecord
from monitor.profile import UserProfile, load_profile
from monitor.scraper import CareerPageScraper
from monitor.storage import StateStore

logger = logging.getLogger(__name__)
EASTERN = ZoneInfo("America/New_York")


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
    hour = datetime.now(EASTERN).hour
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
                    if alert_manager.any_success(results):
                        store.log_alert(payload, results)
                        if payload.job_id:
                            CareerPageScraper.merge_seen_job_id(state, payload.job_id)
                        elif payload.pending_hash:
                            state.last_hash = payload.pending_hash
                            state.last_text = payload.pending_text
                        state.last_alerted = payload.detected_at
                        state.alert_count += 1
                        alerts_fired += 1
                        label = payload.job_title or payload.trigger_keyword
                        tier_tag = (
                            f" [{payload.tier}]" if payload.tier != "standard" else ""
                        )
                        print(f"ALERT {company.name} ({label}){tier_tag}")
                    else:
                        logger.warning(
                            "Delivery failed for %s (%s); will retry next poll",
                            company.name,
                            payload.job_title or payload.trigger_keyword,
                        )
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
    store = StateStore(settings.monitor_db_path)
    scraper = CareerPageScraper(settings, profile)
    alert_manager = AlertManager(settings, profile)

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
