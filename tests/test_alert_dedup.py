"""Tests for content-level dedup of re-posted listings."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from monitor.config import Settings
from monitor.companies import INTERN_CYCLE_KEYWORDS, INTERN_LEVEL_KEYWORDS
from monitor.dedup import job_dedup_key
from monitor.models import AlertPayload, CompanyConfig, StateRecord
from monitor.profile import load_profile
from monitor.scraper import CareerPageScraper
from monitor.storage import StateStore


def _board_json(*jobs: tuple[int, str]) -> str:
    return json.dumps(
        {
            "jobs": [
                {
                    "id": job_id,
                    "title": title,
                    "content": "<p>Summer 2027 internship</p>",
                    "absolute_url": f"https://boards.greenhouse.io/waymo/jobs/{job_id}",
                    "departments": [{"name": "Engineering"}],
                    "location": {"name": "Dallas, TX"},
                }
                for job_id, title in jobs
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
        "min_alert_interval": 0,
        "request_timeout": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def store(tmp_path) -> StateStore:
    return StateStore(str(tmp_path / "test.db"))


@pytest.fixture
def company() -> CompanyConfig:
    return CompanyConfig(
        name="Waymo",
        url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    )


def _seeded_state(company: CompanyConfig, seen_ids: list[str]) -> StateRecord:
    return StateRecord(
        company=company.name,
        url=company.url,
        last_hash="seeded",
        last_checked="",
        last_alerted=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        alert_count=0,
        seen_job_ids=json.dumps(seen_ids),
    )


class TestJobDedupKey:
    def test_repost_of_same_role_shares_a_key(self) -> None:
        # Copart cycles this role through new Workday requisition IDs.
        assert job_dedup_key("Copart", "Software Engineering Intern") == job_dedup_key(
            "Copart", "Software Engineer Intern"
        )

    def test_cycle_year_and_season_are_ignored(self) -> None:
        assert job_dedup_key("Waymo", "SWE Intern, Summer 2026") == job_dedup_key(
            "Waymo", "Software Engineer Internship 2027"
        )

    def test_aggregator_title_prefix_is_stripped(self) -> None:
        # Simplify folds the employer into the title; the key must match the
        # same role scraped straight from the company's own board.
        assert job_dedup_key("Copart", "Copart — Software Engineer Intern") == (
            job_dedup_key("Copart", "Software Engineer Intern")
        )

    def test_company_name_without_separator_is_kept(self) -> None:
        assert "apple" in job_dedup_key("Apple", "Apple Systems Software Intern")

    def test_different_roles_do_not_collide(self) -> None:
        assert job_dedup_key("Copart", "Software Engineer Intern") != job_dedup_key(
            "Copart", "Data Science Intern"
        )

    def test_different_employers_do_not_collide(self) -> None:
        assert job_dedup_key("Copart", "Software Engineer Intern") != job_dedup_key(
            "Waymo", "Software Engineer Intern"
        )

    def test_untitled_job_has_no_key(self) -> None:
        assert job_dedup_key("Copart", "") == ""


class TestRepeatAlertSuppression:
    def test_repost_under_new_job_id_is_suppressed(
        self, store: StateStore, company: CompanyConfig
    ) -> None:
        scraper = CareerPageScraper(_settings(), load_profile(), store)
        state = _seeded_state(company, ["1"])

        with patch.object(
            scraper, "fetch", return_value=_board_json((501, "Software Engineer Intern"))
        ):
            first = scraper.poll_company(company, state)
        assert len(first.alerts) == 1
        store.record_alerted_job(first.alerts[0])

        # Same role re-listed under a fresh requisition ID.
        with patch.object(
            scraper,
            "fetch",
            return_value=_board_json((902, "Software Engineering Intern")),
        ):
            second = scraper.poll_company(company, state)

        assert second.alerts == ()
        # Suppressed listings are marked seen so they aren't re-scored forever.
        assert "902" in json.loads(state.seen_job_ids)

    def test_duplicate_reposts_in_one_cycle_alert_once(
        self, store: StateStore, company: CompanyConfig
    ) -> None:
        scraper = CareerPageScraper(_settings(), load_profile(), store)
        state = _seeded_state(company, ["1"])

        with patch.object(
            scraper,
            "fetch",
            return_value=_board_json(
                (1, "Director of Sales"),
                (801, "Software Engineer Intern"),
                (802, "Software Engineering Intern"),
                (803, "Software Engineer Internship"),
            ),
        ):
            result = scraper.poll_company(company, state)

        assert len(result.alerts) == 1
        assert result.alerts[0].job_id == "801"

    def test_distinct_roles_still_alert(
        self, store: StateStore, company: CompanyConfig
    ) -> None:
        scraper = CareerPageScraper(_settings(), load_profile(), store)
        state = _seeded_state(company, ["1"])

        with patch.object(
            scraper,
            "fetch",
            return_value=_board_json(
                (1, "Director of Sales"),
                (801, "Software Engineer Intern"),
                (802, "Machine Learning Intern"),
            ),
        ):
            result = scraper.poll_company(company, state)

        assert {alert.job_id for alert in result.alerts} == {"801", "802"}

    def test_alert_repeats_after_window_expires(
        self, store: StateStore, company: CompanyConfig
    ) -> None:
        scraper = CareerPageScraper(_settings(), load_profile(), store)
        state = _seeded_state(company, ["501"])

        stale = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        store.record_alerted_job(
            AlertPayload(
                company="Waymo",
                url=company.url,
                trigger_keyword="intern",
                detected_at=stale,
                diff_snippet="",
                job_title="Software Engineer Intern",
                dedup_key=job_dedup_key("Waymo", "Software Engineer Intern"),
            )
        )

        with patch.object(
            scraper,
            "fetch",
            return_value=_board_json((902, "Software Engineer Intern")),
        ):
            result = scraper.poll_company(company, state)

        assert len(result.alerts) == 1

    def test_dedup_disabled_by_zero_window(
        self, store: StateStore, company: CompanyConfig
    ) -> None:
        scraper = CareerPageScraper(
            _settings(alert_dedup_window_days=0), load_profile(), store
        )
        state = _seeded_state(company, ["1"])

        with patch.object(
            scraper,
            "fetch",
            return_value=_board_json(
                (1, "Director of Sales"),
                (801, "Software Engineer Intern"),
                (802, "Software Engineering Intern"),
            ),
        ):
            result = scraper.poll_company(company, state)

        assert len(result.alerts) == 2

    def test_scraper_without_store_keeps_alerting(
        self, company: CompanyConfig
    ) -> None:
        scraper = CareerPageScraper(_settings(), load_profile())
        state = _seeded_state(company, ["1"])

        with patch.object(
            scraper,
            "fetch",
            return_value=_board_json(
                (1, "Director of Sales"),
                (801, "Software Engineer Intern"),
                (802, "Machine Learning Intern"),
            ),
        ):
            result = scraper.poll_company(company, state)

        assert len(result.alerts) == 2


class TestAlertedJobsStore:
    def test_record_and_read_back_within_window(self, store: StateStore) -> None:
        now = datetime.now(timezone.utc)
        payload = AlertPayload(
            company="Simplify 2026",
            url="https://example.com",
            trigger_keyword="intern",
            detected_at=now.isoformat(),
            diff_snippet="",
            job_title="Copart — Software Engineer Intern",
            dedup_key="copart::software engineer intern",
        )
        store.record_alerted_job(payload)
        store.record_alerted_job(payload)

        since = (now - timedelta(days=30)).isoformat()
        assert store.recent_dedup_keys(since) == {"copart::software engineer intern"}
        assert store.recent_dedup_keys((now + timedelta(days=1)).isoformat()) == set()

    def test_keyless_payload_is_not_recorded(self, store: StateStore) -> None:
        store.record_alerted_job(
            AlertPayload(
                company="Waymo",
                url="https://example.com",
                trigger_keyword="intern",
                detected_at=datetime.now(timezone.utc).isoformat(),
                diff_snippet="",
            )
        )
        assert store.recent_dedup_keys("1970-01-01T00:00:00+00:00") == set()
