from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock, Semaphore
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import schedule

from monitor.alerts import AlertManager
from monitor.companies import COMPANIES
from monitor.config import Settings, get_settings, setup_logging
from monitor.diagnostics import ntfy_reachable, run_network_probe
from monitor.models import CompanyConfig, PollResult, StateRecord
from monitor.net import force_ipv4
from monitor.profile import UserProfile, load_profile
from monitor.scraper import CareerPageScraper
from monitor.storage import StateStore, start_time

logger = logging.getLogger(__name__)
EASTERN = ZoneInfo("America/New_York")

_last_health_ping_at: datetime | None = None
_poll_cycles_since_last_ping = 0
_last_cycle_companies_checked = 0
_last_successful_poll_at: datetime | None = None

# Reachability watcher: detects when Railway's egress can reach ntfy.sh again
# (i.e. ntfy.sh's IP block on our egress IP has lifted). Logs on state change.
_ntfy_last_reachable: bool | None = None
_NTFY_REACH_CHECK_INTERVAL = 900  # seconds (15 min)


def _watch_ntfy_reachability() -> None:
    global _ntfy_last_reachable
    reachable = ntfy_reachable()
    if reachable and _ntfy_last_reachable is not True:
        logger.info(
            "[reach] NTFY REACHABILITY RESTORED — Railway can reach ntfy.sh "
            "again; alerts/heartbeats will resume automatically"
        )
    elif not reachable and _ntfy_last_reachable is not False:
        logger.info(
            "[reach] ntfy.sh unreachable from Railway (egress IP still blocked)"
        )
    _ntfy_last_reachable = reachable


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
    now = datetime.now(EASTERN)
    # On weekends, poll at the slower overnight cadence all day long.
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return settings.poll_interval_overnight
    if settings.business_hours_start <= now.hour < settings.business_hours_end:
        return settings.poll_interval_business
    return settings.poll_interval_overnight


def _company_netloc(company: CompanyConfig) -> str:
    return urlparse(company.url).netloc.lower()


def _build_domain_semaphores(
    companies: list[CompanyConfig],
    max_concurrent: int,
) -> dict[str, Semaphore]:
    limit = max(1, max_concurrent)
    netlocs = {_company_netloc(company) for company in companies}
    return {netloc: Semaphore(limit) for netloc in netlocs}


@dataclass(frozen=True, slots=True)
class _PollWorkResult:
    company: CompanyConfig
    state: StateRecord | None
    poll_result: PollResult | None
    error: bool = False


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


def _poll_company_worker(
    scraper: CareerPageScraper,
    store: StateStore,
    company: CompanyConfig,
    domain_semaphores: dict[str, Semaphore],
    semaphore_lock: Lock,
) -> _PollWorkResult:
    try:
        state = store.get_state(company.name) or _default_state(company)
        netloc = _company_netloc(company)
        semaphore = domain_semaphores.get(netloc)
        if semaphore is None:
            with semaphore_lock:
                semaphore = domain_semaphores.setdefault(
                    netloc,
                    Semaphore(1),
                )
        with semaphore:
            poll_result = scraper.poll_company(company, state)
        return _PollWorkResult(company=company, state=state, poll_result=poll_result)
    except Exception:
        logger.exception("Poll cycle failed for %s", company.name)
        return _PollWorkResult(company=company, state=None, poll_result=None, error=True)


def _commit_poll_result(
    company: CompanyConfig,
    state: StateRecord,
    poll_result: PollResult,
    store: StateStore,
    alert_manager: AlertManager,
) -> int:
    alerts_fired = 0

    for closed in poll_result.closed_jobs:
        store.log_closed_job(closed)

    if poll_result.alerts:
        for payload in poll_result.alerts:
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
                store.upsert_state(state)
                label = payload.job_title or payload.trigger_keyword
                tier_tag = f" [{payload.tier}]" if payload.tier != "standard" else ""
                print(f"ALERT {company.name} ({label}){tier_tag}")
            else:
                # Delivery failed (e.g. push endpoint unreachable). Advance the
                # seen-state anyway so this job isn't re-detected and re-sent
                # every cycle. An unbounded retry backlog hammers the push
                # endpoint and can get the egress IP rate-limit-banned, which
                # then keeps *all* delivery failing. Best-effort, at-most-once.
                if payload.job_id:
                    CareerPageScraper.merge_seen_job_id(state, payload.job_id)
                elif payload.pending_hash:
                    state.last_hash = payload.pending_hash
                    state.last_text = payload.pending_text
                logger.warning(
                    "Delivery failed for %s (%s); marking seen to avoid retry storm",
                    company.name,
                    payload.job_title or payload.trigger_keyword,
                )
    else:
        print(f"OK   {company.name}")

    store.upsert_state(state)
    return alerts_fired


def _run_poll_cycle_parallel(
    scraper: CareerPageScraper,
    store: StateStore,
    alert_manager: AlertManager,
    enabled: list[CompanyConfig],
    settings: Settings,
) -> tuple[int, bool]:
    domain_semaphores = _build_domain_semaphores(
        enabled,
        settings.poll_domain_max_concurrent,
    )
    semaphore_lock = Lock()
    alerts_fired = 0
    cycle_had_success = False

    with ThreadPoolExecutor(max_workers=settings.poll_workers) as executor:
        futures = [
            executor.submit(
                _poll_company_worker,
                scraper,
                store,
                company,
                domain_semaphores,
                semaphore_lock,
            )
            for company in enabled
        ]
        for future in as_completed(futures):
            work = future.result()
            if work.error or work.state is None or work.poll_result is None:
                print(f"ERR  {work.company.name}")
                continue

            alerts_fired += _commit_poll_result(
                work.company,
                work.state,
                work.poll_result,
                store,
                alert_manager,
            )
            cycle_had_success = True

    return alerts_fired, cycle_had_success


def run_poll_cycle(
    scraper: CareerPageScraper,
    store: StateStore,
    alert_manager: AlertManager,
    companies: list[CompanyConfig],
    settings: Settings | None = None,
) -> None:
    global _poll_cycles_since_last_ping, _last_cycle_companies_checked, _last_successful_poll_at

    settings = settings or get_settings()
    enabled = [c for c in companies if c.enabled]

    if settings.poll_workers > 1 and len(enabled) > 1:
        alerts_fired, cycle_had_success = _run_poll_cycle_parallel(
            scraper,
            store,
            alert_manager,
            enabled,
            settings,
        )
    else:
        alerts_fired = 0
        cycle_had_success = False

        for company in enabled:
            try:
                state = store.get_state(company.name) or _default_state(company)
                poll_result = scraper.poll_company(company, state)
                alerts_fired += _commit_poll_result(
                    company,
                    state,
                    poll_result,
                    store,
                    alert_manager,
                )
                cycle_had_success = True
            except Exception:
                logger.exception("Poll cycle failed for %s", company.name)
                print(f"ERR  {company.name}")

    if cycle_had_success:
        _poll_cycles_since_last_ping += 1
        _last_cycle_companies_checked = len(enabled)
        _last_successful_poll_at = datetime.now(timezone.utc)

    print(f"Checked {len(enabled)} companies, {alerts_fired} alerts fired.")
    _maybe_send_health_ping(alert_manager, settings)


def _maybe_send_health_ping(alert_manager: AlertManager, settings: Settings) -> None:
    global _last_health_ping_at, _poll_cycles_since_last_ping

    if not settings.health_ping_enabled:
        return
    if _poll_cycles_since_last_ping < 1:
        return

    now = datetime.now(timezone.utc)
    if _last_health_ping_at is not None:
        elapsed = (now - _last_health_ping_at).total_seconds()
        if elapsed < settings.health_ping_interval_seconds:
            return

    uptime_hours = (now - start_time).total_seconds() / 3600
    last_poll_at = (
        _last_successful_poll_at.isoformat() if _last_successful_poll_at else None
    )
    if alert_manager.send_health_ping(
        uptime_hours=uptime_hours,
        companies_checked=_last_cycle_companies_checked,
        last_poll_at=last_poll_at,
    ):
        _last_health_ping_at = now
        _poll_cycles_since_last_ping = 0


def _poll_and_reschedule(
    scraper: CareerPageScraper,
    store: StateStore,
    alert_manager: AlertManager,
    settings: Settings,
) -> None:
    run_poll_cycle(scraper, store, alert_manager, COMPANIES, settings)
    schedule.clear()
    interval = get_poll_interval(settings)
    schedule.every(interval).seconds.do(
        _poll_and_reschedule, scraper, store, alert_manager, settings
    )
    logger.info("Next poll in %d seconds", interval)


def main() -> None:
    setup_logging()
    force_ipv4()
    if os.getenv("NET_PROBE"):  # opt-in one-time startup egress diagnostic
        run_network_probe()
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
        _watch_ntfy_reachability()  # log initial reachability state
        next_reach_check = time.monotonic() + _NTFY_REACH_CHECK_INTERVAL
        while True:
            schedule.run_pending()
            if time.monotonic() >= next_reach_check:
                _watch_ntfy_reachability()
                next_reach_check = time.monotonic() + _NTFY_REACH_CHECK_INTERVAL
            time.sleep(1)
    except KeyboardInterrupt:
        print("Monitor stopped.")


if __name__ == "__main__":
    main()
