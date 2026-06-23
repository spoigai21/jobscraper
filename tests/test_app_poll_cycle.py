"""Tests for run_poll_cycle alert commit behavior and parallel polling."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from monitor.app import run_poll_cycle
from monitor.companies import INTERN_CYCLE_KEYWORDS, INTERN_LEVEL_KEYWORDS
from monitor.models import CompanyConfig, PollResult, StateRecord
from monitor.scraper import CareerPageScraper

GREENHOUSE_BOARD_JSON = json.dumps(
    {
        "jobs": [
            {
                "id": 501,
                "title": "Software Engineering Intern Summer 2027",
                "content": "<p>Python internship</p>",
                "absolute_url": "https://boards.greenhouse.io/waymo/jobs/501",
                "departments": [{"name": "Engineering"}],
                "location": {"name": "Mountain View, CA"},
            }
        ]
    }
)


def _settings(**overrides: object):
    from monitor.config import Settings

    defaults = {
        "twilio_account_sid": "test_sid",
        "twilio_auth_token": "test_token",
        "twilio_from_number": "+15550001001",
        "twilio_to_number": "+15550001002",
        "ntfy_topic": "test-topic",
        "alert_email_to": "test@example.com",
        "min_alert_interval": 3600,
        "request_timeout": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestRunPollCycle:
    def test_delivery_failure_retries_without_consuming_job_id(self) -> None:
        company = CompanyConfig(
            name="Waymo",
            url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
            level_keywords=INTERN_LEVEL_KEYWORDS,
            cycle_keywords=INTERN_CYCLE_KEYWORDS,
            enabled=True,
        )
        state = StateRecord(
            company="Waymo",
            url=company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=None,
            alert_count=0,
            seen_job_ids='["999"]',
        )

        store = MagicMock()
        store.get_state.return_value = state

        from monitor.profile import load_profile

        scraper = CareerPageScraper(_settings(), load_profile())
        alert_manager = MagicMock()
        alert_manager.fire.return_value = {
            "sms": False,
            "call": False,
            "push": False,
            "email": False,
        }
        alert_manager.any_success.return_value = False

        with patch.object(scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            run_poll_cycle(scraper, store, alert_manager, [company])

        assert json.loads(state.seen_job_ids) == []
        assert state.last_alerted is None
        assert state.alert_count == 0
        store.log_alert.assert_not_called()

    def test_delivery_partial_success_commits_job_id(self) -> None:
        company = CompanyConfig(
            name="Waymo",
            url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
            level_keywords=INTERN_LEVEL_KEYWORDS,
            cycle_keywords=INTERN_CYCLE_KEYWORDS,
            enabled=True,
        )
        state = StateRecord(
            company="Waymo",
            url=company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=2,
            seen_job_ids='["999"]',
        )

        store = MagicMock()
        store.get_state.return_value = state

        from monitor.profile import load_profile

        scraper = CareerPageScraper(_settings(), load_profile())
        alert_manager = MagicMock()
        alert_manager.fire.return_value = {
            "sms": False,
            "call": False,
            "push": True,
            "email": False,
        }
        alert_manager.any_success.return_value = True

        with patch.object(scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            run_poll_cycle(scraper, store, alert_manager, [company])

        assert set(json.loads(state.seen_job_ids)) == {"501"}
        assert state.last_alerted is not None
        assert state.alert_count == 3
        store.log_alert.assert_called_once()


def _company(name: str, url: str | None = None) -> CompanyConfig:
    return CompanyConfig(
        name=name,
        url=url or f"https://example.com/{name.lower()}/jobs",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    )


class TestRunPollCycleParallel:
    def test_poll_workers_four_polls_all_companies(self) -> None:
        companies = [_company(f"Co{i}") for i in range(4)]
        polled: list[str] = []
        poll_lock = threading.Lock()

        store = MagicMock()
        store.get_state.return_value = None

        scraper = MagicMock()

        def _poll(company: CompanyConfig, state: StateRecord) -> PollResult:
            with poll_lock:
                polled.append(company.name)
            time.sleep(0.05)
            state.last_checked = datetime.now(timezone.utc).isoformat()
            return PollResult()

        scraper.poll_company.side_effect = _poll
        alert_manager = MagicMock()

        started = time.monotonic()
        run_poll_cycle(
            scraper,
            store,
            alert_manager,
            companies,
            _settings(poll_workers=4),
        )
        elapsed = time.monotonic() - started

        assert set(polled) == {company.name for company in companies}
        assert elapsed < 0.18
        assert store.upsert_state.call_count == len(companies)

    def test_one_company_exception_does_not_kill_others(self) -> None:
        companies = [_company("Good"), _company("Bad"), _company("AlsoGood")]

        store = MagicMock()
        store.get_state.return_value = None

        scraper = MagicMock()

        def _poll(company: CompanyConfig, state: StateRecord) -> PollResult:
            if company.name == "Bad":
                raise RuntimeError("simulated poll failure")
            state.last_checked = datetime.now(timezone.utc).isoformat()
            return PollResult()

        scraper.poll_company.side_effect = _poll
        alert_manager = MagicMock()

        run_poll_cycle(
            scraper,
            store,
            alert_manager,
            companies,
            _settings(poll_workers=4),
        )

        upserted = {call.args[0].company for call in store.upsert_state.call_args_list}
        assert upserted == {"Good", "AlsoGood"}
        assert scraper.poll_company.call_count == len(companies)

    def test_poll_workers_one_uses_sequential_path(self) -> None:
        companies = [_company("Alpha"), _company("Beta")]
        call_order: list[str] = []

        store = MagicMock()
        store.get_state.return_value = None

        scraper = MagicMock()

        def _poll(company: CompanyConfig, state: StateRecord) -> PollResult:
            call_order.append(company.name)
            state.last_checked = datetime.now(timezone.utc).isoformat()
            return PollResult()

        scraper.poll_company.side_effect = _poll
        alert_manager = MagicMock()

        run_poll_cycle(
            scraper,
            store,
            alert_manager,
            companies,
            _settings(poll_workers=1),
        )

        assert call_order == ["Alpha", "Beta"]
        assert store.upsert_state.call_count == 2
