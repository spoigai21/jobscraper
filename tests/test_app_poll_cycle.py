"""Tests for run_poll_cycle alert commit behavior."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from monitor.app import run_poll_cycle
from monitor.models import CompanyConfig, StateRecord
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
        "gmail_address": "test@example.com",
        "gmail_app_password": "test_password",
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
            keywords=["intern", "2027"],
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

        assert json.loads(state.seen_job_ids) == ["999"]
        assert state.last_alerted is None
        assert state.alert_count == 0
        store.log_alert.assert_not_called()

    def test_delivery_partial_success_commits_job_id(self) -> None:
        company = CompanyConfig(
            name="Waymo",
            url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
            keywords=["intern", "2027"],
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

        assert set(json.loads(state.seen_job_ids)) == {"501", "999"}
        assert state.last_alerted is not None
        assert state.alert_count == 3
        store.log_alert.assert_called_once()
