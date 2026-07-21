"""Tests for the first-sight age filter on stale aggregator listings."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from monitor.config import Settings
from monitor.companies import INTERN_CYCLE_KEYWORDS, INTERN_LEVEL_KEYWORDS
from monitor.models import CompanyConfig, StateRecord
from monitor.parsers.simplify import parse_simplify, simplify_listings_url
from monitor.profile import load_profile
from monitor.scraper import CareerPageScraper


def _entry(listing_id: str, days_old: float, title: str = "Software Engineer Intern") -> dict:
    posted = datetime.now(timezone.utc) - timedelta(days=days_old)
    return {
        "id": listing_id,
        "company_name": "Copart",
        "title": title,
        "active": True,
        "is_visible": True,
        "url": f"https://copart.example.com/{listing_id}",
        "terms": ["Summer 2027"],
        "category": "Software Engineering",
        "degrees": ["Bachelor's"],
        "locations": ["Dallas, TX"],
        "date_posted": int(posted.timestamp()),
    }


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
def simplify_company() -> CompanyConfig:
    return CompanyConfig(
        name="Simplify 2027",
        url=simplify_listings_url(2027),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    )


def _seeded_state(company: CompanyConfig) -> StateRecord:
    return StateRecord(
        company=company.name,
        url=company.url,
        last_hash="seeded",
        last_checked="",
        last_alerted=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        alert_count=0,
        seen_job_ids='["seed-1"]',
    )


class TestSimplifyPostedAt:
    def test_parses_date_posted_to_iso(self) -> None:
        raw = json.dumps([_entry("abc", days_old=3)])
        job = parse_simplify(raw, "Simplify 2027")[0]
        posted = datetime.fromisoformat(job.posted_at)
        assert posted.tzinfo is not None
        age_days = (datetime.now(timezone.utc) - posted).total_seconds() / 86400
        assert 2.9 < age_days < 3.1

    @pytest.mark.parametrize("value", [None, "", "not-a-date", 0, -1, 10**18])
    def test_unusable_date_yields_empty_posted_at(self, value: object) -> None:
        entry = _entry("abc", days_old=1)
        entry["date_posted"] = value
        job = parse_simplify(json.dumps([entry]), "Simplify 2027")[0]
        assert job.posted_at == ""


class TestFirstSightAgeFilter:
    def test_stale_listing_is_skipped(
        self, simplify_company: CompanyConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        scraper = CareerPageScraper(_settings(), load_profile())
        state = _seeded_state(simplify_company)
        raw = json.dumps([_entry("old-1", days_old=90)])

        with patch.object(scraper, "fetch", return_value=raw):
            with caplog.at_level("INFO"):
                result = scraper.poll_company(simplify_company, state)

        assert result.alerts == ()
        # Marked seen so it isn't re-evaluated on every future poll.
        assert "old-1" in json.loads(state.seen_job_ids)
        assert "older than 14 days" in caplog.text

    def test_fresh_listing_still_alerts(self, simplify_company: CompanyConfig) -> None:
        scraper = CareerPageScraper(_settings(), load_profile())
        state = _seeded_state(simplify_company)
        raw = json.dumps([_entry("new-1", days_old=0.5)])

        with patch.object(scraper, "fetch", return_value=raw):
            result = scraper.poll_company(simplify_company, state)

        assert len(result.alerts) == 1
        assert result.alerts[0].job_id == "new-1"

    def test_listing_just_inside_window_alerts(
        self, simplify_company: CompanyConfig
    ) -> None:
        scraper = CareerPageScraper(_settings(), load_profile())
        state = _seeded_state(simplify_company)
        raw = json.dumps([_entry("edge-1", days_old=13.9)])

        with patch.object(scraper, "fetch", return_value=raw):
            result = scraper.poll_company(simplify_company, state)

        assert len(result.alerts) == 1

    def test_bulk_reindex_of_old_listings_is_silent(
        self, simplify_company: CompanyConfig
    ) -> None:
        scraper = CareerPageScraper(_settings(), load_profile())
        state = _seeded_state(simplify_company)
        raw = json.dumps(
            [
                _entry(f"old-{i}", days_old=30 + i, title=f"Software Engineer Intern {i}")
                for i in range(25)
            ]
            + [_entry("fresh-1", days_old=0.2, title="Machine Learning Intern")]
        )

        with patch.object(scraper, "fetch", return_value=raw):
            result = scraper.poll_company(simplify_company, state)

        assert [alert.job_id for alert in result.alerts] == ["fresh-1"]

    def test_filter_disabled_by_zero(self, simplify_company: CompanyConfig) -> None:
        scraper = CareerPageScraper(
            _settings(max_new_listing_age_days=0), load_profile()
        )
        state = _seeded_state(simplify_company)
        raw = json.dumps([_entry("old-1", days_old=200)])

        with patch.object(scraper, "fetch", return_value=raw):
            result = scraper.poll_company(simplify_company, state)

        assert len(result.alerts) == 1

    def test_first_seed_is_unaffected(self, simplify_company: CompanyConfig) -> None:
        scraper = CareerPageScraper(_settings(), load_profile())
        state = StateRecord(
            company=simplify_company.name,
            url=simplify_company.url,
            last_hash="",
            last_checked="",
            last_alerted=None,
            alert_count=0,
        )
        raw = json.dumps([_entry("old-1", days_old=90), _entry("new-1", days_old=0.1)])

        with patch.object(scraper, "fetch", return_value=raw):
            result = scraper.poll_company(simplify_company, state)

        assert result.alerts == ()
        assert set(json.loads(state.seen_job_ids)) == {"old-1", "new-1"}

    def test_boards_without_dates_are_never_age_filtered(self) -> None:
        # Greenhouse and friends report no publish date; those jobs must still
        # alert no matter how long the role has been open.
        company = CompanyConfig(
            name="Waymo",
            url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
            level_keywords=INTERN_LEVEL_KEYWORDS,
            cycle_keywords=INTERN_CYCLE_KEYWORDS,
            enabled=True,
        )
        scraper = CareerPageScraper(_settings(), load_profile())
        state = _seeded_state(company)
        raw = json.dumps(
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

        with patch.object(scraper, "fetch", return_value=raw):
            result = scraper.poll_company(company, state)

        assert len(result.alerts) == 1
