"""Tests for NASA STEM Gateway scraper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from monitor.config import Settings
from monitor.models import JobPosting
from monitor.parsers.nasa import (
    NasaScraper,
    discover_listing_pages,
    is_nasa_company,
    is_swe_related,
    parse_nasa_html,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SAMPLE_HTML = (_FIXTURES / "nasa_opportunities.html").read_text(encoding="utf-8")


def _test_settings(**overrides: object) -> Settings:
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


class TestIsSweRelated:
    def test_matches_software_roles(self) -> None:
        assert is_swe_related("Software Engineering Intern")
        assert is_swe_related("Computer Science Research Intern")
        assert is_swe_related("Robotics embedded systems")

    def test_rejects_non_technical_roles(self) -> None:
        assert not is_swe_related("Biology Laboratory Intern")
        assert not is_swe_related("Communications and outreach intern")


class TestIsNasaCompany:
    def test_recognizes_nasa_and_jpl(self) -> None:
        assert is_nasa_company("NASA")
        assert is_nasa_company("JPL")
        assert not is_nasa_company("SpaceX")


class TestParseNasaHtml:
    def test_parses_job_posting_fields(self) -> None:
        jobs = parse_nasa_html(_SAMPLE_HTML, "NASA", swe_only=False)

        assert len(jobs) == 4
        swe_job = next(job for job in jobs if "Software Engineering" in job.title)
        assert isinstance(swe_job, JobPosting)
        assert swe_job.id == "a0B3d000001SWE1"
        assert swe_job.company_name == "NASA"
        assert swe_job.department == "OSTEM Internship"
        assert "Goddard" in swe_job.location
        assert swe_job.url.endswith("/public/s/course-offering/a0B3d000001SWE1")
        assert "flight software" in swe_job.description.lower()

    def test_filters_non_swe_internships_by_default(self) -> None:
        jobs = parse_nasa_html(_SAMPLE_HTML, "NASA")

        titles = {job.title for job in jobs}
        assert "Biology Laboratory Intern" not in titles
        assert "Software Engineering Intern - Summer 2027" in titles
        assert "Computer Science Research Intern" in titles
        assert "Robotics Software Intern" in titles

    def test_jpl_center_filter(self) -> None:
        jobs = parse_nasa_html(_SAMPLE_HTML, "JPL")

        assert len(jobs) == 1
        assert jobs[0].title == "Robotics Software Intern"
        assert "Jet Propulsion Laboratory" in jobs[0].location

    def test_article_fallback_without_custom_element(self) -> None:
        html = """
        <html><body>
          <article>
            <h2>Electrical Engineering Intern</h2>
            <span class="slds-button_neutral">Langley Research Center</span>
            <p class="opportunity-description">Circuit design for avionics systems.</p>
            <a href="/public/s/course-offering/a0BEE001">Apply</a>
          </article>
        </body></html>
        """
        jobs = parse_nasa_html(html, "NASA")

        assert len(jobs) == 1
        assert jobs[0].title == "Electrical Engineering Intern"
        assert jobs[0].id == "a0BEE001"


class TestDiscoverListingPages:
    def test_finds_pagination_links(self) -> None:
        pages = discover_listing_pages(_SAMPLE_HTML)

        assert "https://stemgateway.nasa.gov/public/s/explore-opportunities" in pages
        assert any("page=2" in page for page in pages)


class TestNasaScraper:
    @pytest.fixture
    def scraper(self) -> NasaScraper:
        return NasaScraper(_test_settings())

    def test_fetch_listings_parses_fixture_html(self, scraper: NasaScraper) -> None:
        with patch.object(scraper, "fetch", return_value=_SAMPLE_HTML):
            jobs = scraper.fetch_listings("NASA")

        assert len(jobs) == 3
        assert all(is_swe_related(job.title) or is_swe_related(job.description) for job in jobs)

    def test_fetch_listings_returns_empty_on_fetch_failure(
        self, scraper: NasaScraper
    ) -> None:
        with patch.object(scraper, "fetch", return_value=None):
            assert scraper.fetch_listings("NASA") == []
