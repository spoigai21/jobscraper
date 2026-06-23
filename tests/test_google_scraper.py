"""Tests for Google Careers AF_initDataCallback parser."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from monitor.parsers.google import (
    fetch_google_search_raw,
    google_page_url,
    is_google_careers_url,
    parse_google,
    parse_google_html,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SEARCH_URL = "https://careers.google.com/jobs/results/?employment_type=INTERN"


def _google_ds1_html(jobs: list[list]) -> str:
    payload = json.dumps([jobs], ensure_ascii=False)
    return (
        "<html><body><script>"
        f"AF_initDataCallback({{key: 'ds:1', hash: '2', data:{payload}}});"
        "</script></body></html>"
    )


def _minimal_google_job(job_id: str, title: str) -> list:
    return [
        job_id,
        title,
        "",
        None,
        None,
        "",
        None,
        "",
        "",
        [[f"{title} Location", [], "City", None, "CA", "US"]],
    ]


class TestGoogleUrlHelpers:
    def test_detects_careers_search_url(self) -> None:
        url = "https://careers.google.com/jobs/results/?employment_type=INTERN"
        assert is_google_careers_url(url)

    def test_detects_careers_jobs_path(self) -> None:
        assert is_google_careers_url("https://careers.google.com/jobs/results/123-slug/")

    def test_rejects_unrelated_url(self) -> None:
        assert not is_google_careers_url("https://www.google.com/about/careers/applications/")

    def test_sets_page_query_param(self) -> None:
        page_url = google_page_url(_SEARCH_URL, page=3)
        assert "page=3" in page_url
        assert "employment_type=INTERN" in page_url


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


class TestParseGoogle:
    def test_parses_paginated_json_payload(self) -> None:
        payload = {
            "jobs": [
                _minimal_google_job("140245524367188678", "Student Researcher"),
                _minimal_google_job("138205674881327814", "Solutions Architect"),
            ]
        }
        jobs = parse_google(json.dumps(payload), "Google")

        assert len(jobs) == 2
        assert jobs[0].id == "140245524367188678"
        assert jobs[1].title == "Solutions Architect"


class TestFetchGoogleSearchRaw:
    @patch("monitor.parsers.google.time.sleep")
    def test_paginates_until_empty_page(self, _sleep: MagicMock) -> None:
        full_page_jobs = [
            _minimal_google_job(f"14024552436718{index}", f"Intern Role {index}")
            for index in range(20)
        ]
        page_one = MagicMock()
        page_one.text = _google_ds1_html(full_page_jobs)
        page_one.raise_for_status = MagicMock()

        page_two = MagicMock()
        page_two.text = _google_ds1_html([])
        page_two.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.side_effect = [page_one, page_two]

        with patch("monitor.parsers.google.requests.Session", return_value=mock_session):
            raw = fetch_google_search_raw(
                _SEARCH_URL,
                user_agent="test-agent",
                timeout=5,
            )

        assert raw is not None
        payload = json.loads(raw)
        assert len(payload["jobs"]) == 20
        assert mock_session.get.call_count == 2
        assert "page=1" in mock_session.get.call_args_list[0].args[0]
        assert "page=2" in mock_session.get.call_args_list[1].args[0]
        _sleep.assert_called_once()

    @patch("monitor.parsers.google.time.sleep")
    def test_stops_when_page_returns_no_new_jobs(self, _sleep: MagicMock) -> None:
        duplicate_jobs = [
            _minimal_google_job("140245524367188678", "Student Researcher"),
        ]
        page_one = MagicMock()
        page_one.text = _google_ds1_html(duplicate_jobs)
        page_one.raise_for_status = MagicMock()

        page_two = MagicMock()
        page_two.text = _google_ds1_html(duplicate_jobs)
        page_two.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.side_effect = [page_one, page_two]

        with patch("monitor.parsers.google.requests.Session", return_value=mock_session):
            raw = fetch_google_search_raw(
                _SEARCH_URL,
                user_agent="test-agent",
                timeout=5,
            )

        assert raw is not None
        payload = json.loads(raw)
        assert len(payload["jobs"]) == 1
        assert mock_session.get.call_count == 2
        _sleep.assert_called_once()

    @patch("monitor.parsers.google.time.sleep")
    def test_dedupes_jobs_across_pages(self, _sleep: MagicMock) -> None:
        page_one_jobs = [
            _minimal_google_job("140245524367188678", "Student Researcher"),
            _minimal_google_job("138205674881327814", "Solutions Architect"),
        ]
        page_two_jobs = [
            _minimal_google_job("138205674881327814", "Solutions Architect"),
            _minimal_google_job("999999999999999999", "New Intern Role"),
        ]

        page_one = MagicMock()
        page_one.text = _google_ds1_html(page_one_jobs)
        page_one.raise_for_status = MagicMock()

        page_two = MagicMock()
        page_two.text = _google_ds1_html(page_two_jobs)
        page_two.raise_for_status = MagicMock()

        page_three = MagicMock()
        page_three.text = _google_ds1_html([])
        page_three.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.side_effect = [page_one, page_two, page_three]

        with patch("monitor.parsers.google.requests.Session", return_value=mock_session):
            raw = fetch_google_search_raw(
                _SEARCH_URL,
                user_agent="test-agent",
                timeout=5,
            )

        assert raw is not None
        payload = json.loads(raw)
        assert len(payload["jobs"]) == 3
        job_ids = {job[0] for job in payload["jobs"]}
        assert job_ids == {
            "140245524367188678",
            "138205674881327814",
            "999999999999999999",
        }
        assert mock_session.get.call_count == 3
        assert _sleep.call_count == 2
