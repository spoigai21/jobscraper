"""Tests for stale seen_job_ids cleanup and closed listing detection."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from monitor.config import Settings
from monitor.models import CompanyConfig, StateRecord
from monitor.profile import load_profile
from monitor.scraper import CareerPageScraper
from monitor.storage import StateStore

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

GREENHOUSE_TWO_JOBS_JSON = json.dumps(
    {
        "jobs": [
            {
                "id": 501,
                "title": "Software Engineering Intern Summer 2027",
                "content": "<p>Python internship</p>",
                "absolute_url": "https://boards.greenhouse.io/waymo/jobs/501",
                "departments": [{"name": "Engineering"}],
                "location": {"name": "Mountain View, CA"},
            },
            {
                "id": 777,
                "title": "Director of Sales",
                "content": "<p>Leadership role</p>",
                "absolute_url": "https://boards.greenhouse.io/waymo/jobs/777",
                "departments": [{"name": "Sales"}],
                "location": {"name": "Mountain View, CA"},
            },
        ]
    }
)


def _settings(**overrides: object) -> Settings:
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


@pytest.fixture
def greenhouse_company() -> CompanyConfig:
    return CompanyConfig(
        name="Waymo",
        url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
        keywords=["intern", "2027"],
        enabled=True,
    )


@pytest.fixture
def profiled_scraper() -> CareerPageScraper:
    return CareerPageScraper(_settings(), load_profile())


class TestStaleSeenJobIdsCleanup:
    def test_first_seed_does_not_prune(
        self,
        profiled_scraper: CareerPageScraper,
        greenhouse_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Waymo",
            url=greenhouse_company.url,
            last_hash="",
            last_checked="",
            last_alerted=None,
            alert_count=0,
        )

        with patch.object(
            profiled_scraper, "fetch", return_value=GREENHOUSE_TWO_JOBS_JSON
        ):
            result = profiled_scraper.poll_company(greenhouse_company, state)

        assert result.alerts == ()
        assert set(json.loads(state.seen_job_ids)) == {"501", "777"}

    def test_removes_stale_seen_ids_not_on_board(
        self,
        profiled_scraper: CareerPageScraper,
        greenhouse_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Waymo",
            url=greenhouse_company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["501", "999"]',
            seen_job_titles='{"501": "Software Engineering Intern Summer 2027", "999": "Old Intern Role"}',
        )

        with patch.object(profiled_scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            result = profiled_scraper.poll_company(greenhouse_company, state)

        assert result.alerts == ()
        assert json.loads(state.seen_job_ids) == ["501"]
        titles = json.loads(state.seen_job_titles)
        assert "999" not in titles
        assert titles["501"] == "Software Engineering Intern Summer 2027"


class TestClosedListingDetection:
    def test_detects_closed_job_with_known_title(
        self,
        profiled_scraper: CareerPageScraper,
        greenhouse_company: CompanyConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        state = StateRecord(
            company="Waymo",
            url=greenhouse_company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["501", "999"]',
            seen_job_titles='{"999": "Retired Intern Role"}',
        )

        with patch.object(profiled_scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            with caplog.at_level("INFO"):
                result = profiled_scraper.poll_company(greenhouse_company, state)

        assert result.alerts == ()
        assert len(result.closed_jobs) == 1
        closed = result.closed_jobs[0]
        assert closed.job_id == "999"
        assert closed.job_title == "Retired Intern Role"
        assert closed.company == "Waymo"
        assert "Job closed for Waymo: Retired Intern Role (999)" in caplog.text

    def test_closed_job_unknown_title_when_not_in_map(
        self,
        profiled_scraper: CareerPageScraper,
        greenhouse_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Waymo",
            url=greenhouse_company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["501", "888"]',
        )

        with patch.object(profiled_scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            result = profiled_scraper.poll_company(greenhouse_company, state)

        assert len(result.closed_jobs) == 1
        assert result.closed_jobs[0].job_title == "unknown"

    def test_closed_jobs_persisted_in_sqlite(
        self,
        profiled_scraper: CareerPageScraper,
        greenhouse_company: CompanyConfig,
        tmp_path,
    ) -> None:
        db_path = tmp_path / "monitor.db"
        store = StateStore(str(db_path))
        state = StateRecord(
            company="Waymo",
            url=greenhouse_company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["501", "999"]',
            seen_job_titles='{"999": "Closed Intern"}',
        )

        with patch.object(profiled_scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            result = profiled_scraper.poll_company(greenhouse_company, state)

        for closed in result.closed_jobs:
            store.log_closed_job(closed)

        rows = store.get_recent_closed_jobs(limit=5)
        assert len(rows) == 1
        assert rows[0]["company"] == "Waymo"
        assert rows[0]["job_id"] == "999"
        assert rows[0]["job_title"] == "Closed Intern"
