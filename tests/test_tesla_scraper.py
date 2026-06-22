"""Tests for Tesla careers state parser."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from monitor.config import Settings
from monitor.models import JobPosting
from monitor.parsers.tesla import (
    TeslaScraper,
    _is_blocked_response,
    _is_valid_state_payload,
    is_tesla_company,
    parse_tesla_state,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SAMPLE_STATE = json.loads((_FIXTURES / "tesla_state.json").read_text(encoding="utf-8"))
_DEFAULT_SOURCE_URL = "https://www.tesla.com/careers/search/?type=3&query=intern"


def _test_settings(**overrides: object) -> Settings:
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


class TestIsTeslaCompany:
    def test_recognizes_tesla(self) -> None:
        assert is_tesla_company("Tesla")
        assert not is_tesla_company("SpaceX")


class TestParseTeslaState:
    def test_parses_job_posting_fields(self) -> None:
        jobs = parse_tesla_state(_SAMPLE_STATE, "Tesla", source_url=_DEFAULT_SOURCE_URL)

        assert len(jobs) == 3
        intern_job = next(job for job in jobs if job.id == "12345")
        assert isinstance(intern_job, JobPosting)
        assert intern_job.title == "Software Engineering Intern"
        assert intern_job.department == "Software Engineering"
        assert intern_job.location == "Palo Alto, CA"
        assert intern_job.url.endswith("/software-engineering-intern-12345")
        assert intern_job.company_name == "Tesla"

    def test_filters_by_intern_type_and_query(self) -> None:
        jobs = parse_tesla_state(_SAMPLE_STATE, "Tesla", source_url=_DEFAULT_SOURCE_URL)
        titles = {job.title for job in jobs}

        assert "Production Associate" not in titles
        assert "Firmware Intern" in titles
        assert "Controls Engineering Intern" in titles

    def test_filters_by_site_when_present(self) -> None:
        source_url = "https://www.tesla.com/careers/search/?site=US&type=3&query=intern"
        jobs = parse_tesla_state(_SAMPLE_STATE, "Tesla", source_url=source_url)
        locations = {job.location for job in jobs}

        assert "Berlin, Germany" not in locations
        assert "Palo Alto, CA" in locations
        assert "Austin, TX" in locations

    def test_supports_legacy_department_key(self) -> None:
        payload = {
            "lookup": {"departments": {"5": "Energy"}, "locations": {"1": "Fremont, CA"}},
            "listings": [{"id": "99", "t": "Energy Intern", "d": "5", "l": "1", "y": "3"}],
        }
        jobs = parse_tesla_state(
            payload,
            "Tesla",
            source_url="https://www.tesla.com/careers/search/?type=3",
        )

        assert len(jobs) == 1
        assert jobs[0].department == "Energy"


class TestTeslaResponseHelpers:
    def test_valid_state_payload(self) -> None:
        assert _is_valid_state_payload(json.dumps(_SAMPLE_STATE))
        assert not _is_valid_state_payload("<html>Access Denied</html>")
        assert not _is_valid_state_payload('{"cpr_chlge":"true"}')

    def test_blocked_response_detection(self) -> None:
        assert _is_blocked_response("<HTML><H1>Access Denied</H1></HTML>", 403)
        assert _is_blocked_response('{"cpr_chlge":"true","t":"123"}', 429)
        assert _is_blocked_response(
            '<html><div id="sec-if-cpt-container"></div></html>',
            200,
        )
        assert not _is_blocked_response(json.dumps(_SAMPLE_STATE), 200)


class TestTeslaScraper:
    @pytest.fixture
    def scraper(self) -> TeslaScraper:
        return TeslaScraper(_test_settings())

    def test_fetch_listings_parses_fixture_json(self, scraper: TeslaScraper) -> None:
        raw = json.dumps(_SAMPLE_STATE)
        with patch.object(scraper, "fetch_state", return_value=raw):
            jobs = scraper.fetch_listings("Tesla", source_url=_DEFAULT_SOURCE_URL)

        assert len(jobs) == 3
        assert all("intern" in job.title.casefold() for job in jobs)

    def test_fetch_listings_returns_empty_on_fetch_failure(
        self, scraper: TeslaScraper
    ) -> None:
        with patch.object(scraper, "fetch_state", return_value=None):
            assert scraper.fetch_listings("Tesla") == []

    def test_fetch_state_returns_first_valid_endpoint(self, scraper: TeslaScraper) -> None:
        raw = json.dumps(_SAMPLE_STATE)
        with patch.object(scraper, "_warmup_session"), patch.object(
            scraper,
            "_try_endpoint",
            side_effect=[None, raw],
        ) as mock_try:
            assert scraper.fetch_state(_DEFAULT_SOURCE_URL) == raw
            assert mock_try.call_count == 2
