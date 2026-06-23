"""Tests for Google Careers AF_initDataCallback parser."""

from __future__ import annotations

from pathlib import Path

from monitor.parsers.google import is_google_careers_url, parse_google_html

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestGoogleUrlHelpers:
    def test_detects_careers_search_url(self) -> None:
        url = "https://careers.google.com/jobs/results/?employment_type=INTERN"
        assert is_google_careers_url(url)

    def test_detects_careers_jobs_path(self) -> None:
        assert is_google_careers_url("https://careers.google.com/jobs/results/123-slug/")

    def test_rejects_unrelated_url(self) -> None:
        assert not is_google_careers_url("https://www.google.com/about/careers/applications/")


class TestParseGoogleHtml:
    def test_parses_sample_fixture(self) -> None:
        html = (_FIXTURES / "google_sample.html").read_text(encoding="utf-8")
        jobs = parse_google_html(html, "Google")

        assert len(jobs) == 2
        assert jobs[0].id == "140245524367188678"
        assert jobs[0].title == "Student Researcher, BS/MS, Winter/Summer 2026"
        assert "Mountain View, CA, USA" in jobs[0].location
        assert jobs[0].url == (
            "https://www.google.com/about/careers/applications/jobs/results/"
            "140245524367188678-student-researcher-bs-ms-winter-summer-2026/"
        )
        assert "Participate in research" in jobs[0].description
        assert jobs[0].company_name == "Google"

        assert jobs[1].id == "138205674881327814"
        assert "Advertising Solutions Architect" in jobs[1].title
        assert "Beijing, China" in jobs[1].location

    def test_returns_empty_for_missing_callback(self) -> None:
        jobs = parse_google_html("<html><body>No jobs here</body></html>", "Google")
        assert jobs == []

    def test_strips_html_from_description(self) -> None:
        html = (_FIXTURES / "google_sample.html").read_text(encoding="utf-8")
        jobs = parse_google_html(html, "Google")
        assert "<ul>" not in jobs[0].description
        assert "<h3>" not in jobs[0].description
