"""Tests for Apple Jobs SSR hydration parser."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from monitor.parsers.apple import (
    apple_page_url,
    fetch_apple_search_raw,
    is_apple_jobs_url,
    parse_apple,
    parse_apple_hydration,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SAMPLE_HTML = (_FIXTURES / "apple_sample.html").read_text(encoding="utf-8")
_SEARCH_URL = "https://jobs.apple.com/en-us/search?search=internship&sort=newest"


def _apple_hydration_html(total_records: int, search_results: list[dict]) -> str:
    payload = {
        "loaderData": {
            "search": {
                "totalRecords": total_records,
                "searchResults": search_results,
                "queryParams": {"search": "internship", "sort": "newest"},
            }
        }
    }
    escaped = json.dumps(payload, ensure_ascii=False).replace("\\", "\\\\").replace('"', '\\"')
    return (
        "<html><body><script>"
        f'window.__staticRouterHydrationData = JSON.parse("{escaped}");'
        "</script></body></html>"
    )


def _minimal_apple_job(job_id: str, title: str) -> dict:
    return {
        "reqId": job_id,
        "postingTitle": title,
        "transformedPostingTitle": title.lower().replace(" ", "-"),
        "locations": [{"name": "San Jose"}],
        "team": {"teamName": "Hardware"},
        "jobSummary": "Summary",
    }


class TestAppleUrlHelpers:
    def test_detects_search_url(self) -> None:
        assert is_apple_jobs_url(_SEARCH_URL)

    def test_rejects_non_search_jobs_url(self) -> None:
        assert not is_apple_jobs_url("https://jobs.apple.com/en-us/details/200666594/slug")

    def test_sets_page_query_param(self) -> None:
        page_url = apple_page_url(_SEARCH_URL, page=3)
        assert "page=3" in page_url
        assert "search=internship" in page_url
        assert "sort=newest" in page_url


class TestParseAppleHydration:
    def test_extracts_search_payload_from_fixture(self) -> None:
        search = parse_apple_hydration(_SAMPLE_HTML)

        assert search is not None
        assert search["totalRecords"] == 84
        assert len(search["searchResults"]) == 3
        assert search["queryParams"]["search"] == "internship"

    def test_returns_none_when_hydration_missing(self) -> None:
        assert parse_apple_hydration("<html><body>No hydration</body></html>") is None


class TestParseApple:
    def test_parses_sample_fixture(self) -> None:
        search = parse_apple_hydration(_SAMPLE_HTML)
        assert search is not None

        jobs = parse_apple(search, "Apple")

        assert len(jobs) == 3
        assert jobs[0].id == "200666594-3749"
        assert jobs[0].title == "Hardware System Integrator - Apple Vision Pro"
        assert jobs[0].location == "San Jose"
        assert jobs[0].department == "Hardware"
        assert jobs[0].url == (
            "https://jobs.apple.com/en-us/details/200666594-3749/"
            "hardware-system-integrator-apple-vision-pro"
        )
        assert "Apple Vision Pro" in jobs[0].description
        assert jobs[0].company_name == "Apple"

        assert jobs[1].id == "200632290-0240"
        assert jobs[1].location == "Austin Metro Area"

        assert jobs[2].id == "200494847-3715"
        assert "Intern" in jobs[2].title
        assert jobs[2].location == "Shanghai"

    def test_parses_raw_json_string(self) -> None:
        search = parse_apple_hydration(_SAMPLE_HTML)
        assert search is not None

        jobs = parse_apple(json.dumps(search), "Apple")
        assert len(jobs) == 3


class TestFetchAppleSearchRaw:
    @patch("monitor.parsers.apple.time.sleep")
    def test_paginates_until_short_page(self, _sleep: MagicMock) -> None:
        full_page_jobs = [
            _minimal_apple_job(f"20066659{index}", f"Intern Role {index}")
            for index in range(20)
        ]
        page_one = MagicMock()
        page_one.text = _apple_hydration_html(84, full_page_jobs)
        page_one.raise_for_status = MagicMock()

        page_two = MagicMock()
        page_two.text = _apple_hydration_html(84, [])
        page_two.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.side_effect = [page_one, page_two]

        with patch("monitor.parsers.apple.requests.Session", return_value=mock_session):
            raw = fetch_apple_search_raw(
                _SEARCH_URL,
                user_agent="test-agent",
                timeout=5,
            )

        assert raw is not None
        payload = json.loads(raw)
        assert len(payload["searchResults"]) == 20
        assert payload["totalRecords"] == 84
        assert mock_session.get.call_count == 2
        assert "page=1" in mock_session.get.call_args_list[0].args[0]
        assert "page=2" in mock_session.get.call_args_list[1].args[0]
        _sleep.assert_called_once()

    @patch("monitor.parsers.apple.time.sleep")
    def test_stops_when_page_is_shorter_than_page_size(self, _sleep: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("monitor.parsers.apple.requests.Session", return_value=mock_session):
            raw = fetch_apple_search_raw(
                _SEARCH_URL,
                user_agent="test-agent",
                timeout=5,
            )

        assert raw is not None
        payload = json.loads(raw)
        assert len(payload["searchResults"]) == 3
        assert payload["totalRecords"] == 84
        assert mock_session.get.call_count == 1
        assert "page=1" in mock_session.get.call_args.args[0]
        _sleep.assert_not_called()
