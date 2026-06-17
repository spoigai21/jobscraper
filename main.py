"""Scheduler and daemon entrypoint for the internship monitor."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import schedule
from rich.console import Console

from alerts import AlertManager
from companies import COMPANIES
from config import Settings, get_settings, setup_logging
from models import CompanyConfig, StateRecord
from scraper import CareerPageScraper
from storage import StateStore

logger = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")
console = Console()


def get_poll_interval(settings: Settings | None = None) -> int:
    """Return poll interval in seconds based on current US/Pacific business hours."""
    settings = settings or get_settings()
    now_pacific = datetime.now(PACIFIC)
    hour = now_pacific.hour

    if settings.business_hours_start <= hour < settings.business_hours_end:
        return settings.poll_interval_business

    return settings.poll_interval_overnight


def _default_state(company: CompanyConfig) -> StateRecord:
    """Create initial persisted state for a company that has never been polled."""
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
    """Poll all enabled companies once and dispatch alerts for detected changes."""
    enabled = [company for company in companies if company.enabled]
    alerts_fired = 0

    for company in enabled:
        try:
            state = store.get_state(company.name) or _default_state(company)
            payload = scraper.poll_company(company, state)

            if payload is not None:
                results = alert_manager.fire_all(payload)
                store.log_alert(payload, results)
                alerts_fired += 1
                console.print(
                    f"[yellow]⚠[/yellow] {company.name}: "
                    f"ALERT ({payload.trigger_keyword})"
                )
            else:
                console.print(f"[green]✓[/green] {company.name}: OK")

            store.upsert_state(state)
        except Exception:
            logger.exception("Poll cycle failed for %s", company.name)
            console.print(f"[red]⚠[/red] {company.name}: ERROR")

    console.print(
        f"Checked {len(enabled)} companies. {alerts_fired} alerts fired."
    )


def _poll_and_reschedule(
    scraper: CareerPageScraper,
    store: StateStore,
    alert_manager: AlertManager,
    settings: Settings,
) -> None:
    """Run one poll cycle and reschedule the next run with a fresh interval."""
    run_poll_cycle(scraper, store, alert_manager, COMPANIES)
    schedule.clear()
    interval = get_poll_interval(settings)
    schedule.every(interval).seconds.do(
        _poll_and_reschedule,
        scraper,
        store,
        alert_manager,
        settings,
    )
    logger.info("Next poll scheduled in %d seconds", interval)


def main() -> None:
    """Start the internship monitor daemon."""
    setup_logging()
    settings = get_settings()
    store = StateStore()
    scraper = CareerPageScraper(settings)
    alert_manager = AlertManager(settings)

    logger.info("Internship monitor starting")

    try:
        _poll_and_reschedule(scraper, store, alert_manager, settings)

        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("Monitor stopped.")


if __name__ == "__main__":
    main()
