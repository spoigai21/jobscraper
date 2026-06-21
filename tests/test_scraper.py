"""Tests for CareerPageScraper."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from config import Settings
from models import AlertPayload, CompanyConfig, StateRecord
from profile import load_profile
from scraper import CareerPageScraper, _WORKDAY_PAGE_LIMIT, _WORKDAY_REQUESTED_PAGE_LIMIT


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


def _sample_html(body: str = "Summer Intern 2027 openings") -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <script>window.tracking = true;</script>
  <style>.hidden {{ display: none; }}</style>
</head>
<body>
  <header>Site Header</header>
  <nav>Home | Careers | About</nav>
  <main>{body}</main>
  <footer>Copyright 2027</footer>
</body>
</html>"""


@pytest.fixture
def scraper() -> CareerPageScraper:
    return CareerPageScraper(_test_settings())


@pytest.fixture
def company() -> CompanyConfig:
    return CompanyConfig(
        name="TestCo",
        url="https://example.com/careers",
        keywords=[
            "intern",
            "internship",
            "spring 2027",
            "summer 2027",
            "fall 2027",
            "co-op 2027",
            "co-op",
            "residency",
        ],
        enabled=True,
    )


class TestExtractText:
    def test_strips_noise_tags(self, scraper: CareerPageScraper) -> None:
        text = scraper.extract_text(_sample_html())

        assert "summer intern 2027 openings" in text
        assert "site header" not in text
        assert "home | careers | about" not in text
        assert "copyright 2027" not in text
        assert "window.tracking" not in text
        assert "display: none" not in text

    def test_lowercases_output(self, scraper: CareerPageScraper) -> None:
        text = scraper.extract_text(_sample_html("APPLY FOR Internship NOW"))

        assert text == "apply for internship now"


class TestHashContent:
    def test_deterministic_sha256(self, scraper: CareerPageScraper) -> None:
        text = "summer intern 2027"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()

        assert scraper.hash_content(text) == expected
        assert scraper.hash_content(text) == expected


class TestCheckKeywords:
    def test_case_insensitive_first_match(self, scraper: CareerPageScraper) -> None:
        text = "we are hiring summer INTERN roles for 2027"
        keywords = ["INTERN", "2027", "internship"]

        assert scraper.check_keywords(text, keywords) == "INTERN"

    def test_matches_2027_seasonal_phrases(self, scraper: CareerPageScraper) -> None:
        text = "now accepting applications for summer 2027 and co-op 2027 programs"
        keywords = ["summer 2027", "co-op 2027", "fall 2027"]

        assert scraper.check_keywords(text, keywords) == "summer 2027"

    def test_intern_word_boundary_avoids_internal(self, scraper: CareerPageScraper) -> None:
        assert scraper.check_keywords("internal communications team", ["intern"]) is None
        assert scraper.check_keywords("summer intern program", ["intern"]) == "intern"

    def test_2027_word_boundary(self, scraper: CareerPageScraper) -> None:
        assert scraper.check_keywords("role id 20271 posted", ["2027"]) is None
        assert scraper.check_keywords("summer 2027 internship", ["2027"]) == "2027"

    def test_returns_none_when_no_match(self, scraper: CareerPageScraper) -> None:
        assert scraper.check_keywords(
            "full-time engineer", ["intern", "summer 2027"]
        ) is None


class TestGetDiffSnippet:
    def test_returns_novel_content_up_to_300_chars(
        self, scraper: CareerPageScraper
    ) -> None:
        old_text = "existing jobs listing "
        new_text = old_text + "new summer intern 2027 role added today"

        snippet = scraper.get_diff_snippet(old_text, new_text, ["intern"])

        assert snippet.startswith("New: ")
        assert "new summer intern 2027 role added today" in snippet
        assert len(snippet) <= 300

    def test_truncates_long_novel_content(self, scraper: CareerPageScraper) -> None:
        old_text = "unchanged prefix "
        novel = "x" * 400
        new_text = old_text + novel

        snippet = scraper.get_diff_snippet(old_text, new_text)

        assert snippet.startswith("New: ")
        assert len(snippet) <= 300

    def test_fallback_when_no_novel_content(self, scraper: CareerPageScraper) -> None:
        text = "unchanged content"

        assert scraper.get_diff_snippet(text, text) == "Page content changed"


class TestPollCompany:
    def _state(
        self,
        *,
        last_hash: str = "",
        last_text: str = "",
        last_alerted: str | None = None,
        alert_count: int = 0,
    ) -> StateRecord:
        return StateRecord(
            company="TestCo",
            url="https://example.com/careers",
            last_hash=last_hash,
            last_checked="",
            last_alerted=last_alerted,
            alert_count=alert_count,
            last_text=last_text,
        )

    def test_no_alert_when_hash_unchanged(
        self, scraper: CareerPageScraper, company: CompanyConfig
    ) -> None:
        html = _sample_html()
        text = scraper.extract_text(html)
        content_hash = scraper.hash_content(text)
        state = self._state(last_hash=content_hash, last_text=text)

        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.poll_company(company, state)

        assert result == []
        assert state.last_hash == content_hash
        assert state.alert_count == 0

    def test_no_alert_when_hash_changed_but_no_keyword(
        self, scraper: CareerPageScraper, company: CompanyConfig
    ) -> None:
        html = _sample_html("full-time software engineer roles available now")
        state = self._state(
            last_hash="stale-hash",
            last_text="legacy full-time software engineer listings",
        )

        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.poll_company(company, state)

        assert result == []
        assert state.alert_count == 0

    def test_alert_when_hash_changed_keyword_and_cooldown_passed(
        self, scraper: CareerPageScraper, company: CompanyConfig
    ) -> None:
        html = _sample_html("new summer intern 2027 opening posted today")
        state = self._state(
            last_hash="stale-hash",
            last_text="legacy staff engineer listings only",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=2,
        )

        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.poll_company(company, state)

        assert len(result) == 1
        payload = result[0]
        assert isinstance(payload, AlertPayload)
        assert payload.company == "TestCo"
        assert payload.url == company.url
        assert payload.trigger_keyword == "intern"
        assert payload.diff_snippet.startswith("New: ")
        assert state.alert_count == 3
        assert state.last_alerted is not None

    def test_no_alert_when_within_min_alert_interval(
        self, scraper: CareerPageScraper, company: CompanyConfig
    ) -> None:
        html = _sample_html("new summer intern 2027 opening posted today")
        state = self._state(
            last_hash="stale-hash",
            last_text="legacy staff engineer listings only",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=100)
            ).isoformat(),
        )

        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.poll_company(company, state)

        assert result == []
        assert state.alert_count == 0

    def test_first_poll_with_empty_previous_hash(
        self, scraper: CareerPageScraper, company: CompanyConfig
    ) -> None:
        html = _sample_html("summer intern 2027 program")
        state = self._state(last_hash="")
        expected_text = scraper.extract_text(html)

        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.poll_company(company, state)

        assert result == []
        assert state.last_hash == scraper.hash_content(expected_text)
        assert state.last_text == expected_text
        assert state.alert_count == 0


GREENHOUSE_BOARD_JSON = json.dumps(
    {
        "jobs": [
            {
                "id": 501,
                "title": "Software Engineering Intern Summer 2027",
                "content": "<p>Python and pytorch internship</p>",
                "absolute_url": "https://boards.greenhouse.io/waymo/jobs/501",
                "departments": [{"name": "Engineering"}],
                "location": {"name": "Mountain View, CA"},
            }
        ]
    }
)


class TestPollPerJobBoard:
    @pytest.fixture
    def greenhouse_company(self) -> CompanyConfig:
        return CompanyConfig(
            name="Waymo",
            url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
            keywords=["intern", "2027"],
            enabled=True,
        )

    @pytest.fixture
    def profiled_scraper(self) -> CareerPageScraper:
        return CareerPageScraper(_test_settings(), load_profile())

    def test_first_poll_seeds_job_ids_without_alert(
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

        with patch.object(profiled_scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            result = profiled_scraper.poll_company(greenhouse_company, state)

        assert result == []
        assert json.loads(state.seen_job_ids) == ["501"]

    def test_new_job_emits_scored_alert(
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
            seen_job_ids='["999"]',
        )

        with patch.object(profiled_scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            result = profiled_scraper.poll_company(greenhouse_company, state)

        assert len(result) == 1
        payload = result[0]
        assert payload.job_title == "Software Engineering Intern Summer 2027"
        assert payload.relevance_score > 0
        assert payload.tier in ("standard", "high")
        assert json.loads(state.seen_job_ids) == ["501"]


WORKDAY_URL = (
    "https://example.wd5.myworkdayjobs.com/wday/cxs/example/ExampleSite/jobs"
    "?searchText=software intern"
)


def _workday_posting(title: str, location: str = "Remote") -> dict[str, str]:
    return {
        "title": title,
        "externalPath": f"/job/Remote/{title.replace(' ', '-')}",
        "locationsText": location,
        "postedOn": "Posted Today",
        "bulletFields": ["REF001"],
    }


def _mock_workday_response(
    *,
    status_code: int = 200,
    total: int | None = None,
    postings: list[dict[str, str]] | None = None,
    error_code: str | None = None,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {
        "total": total,
        "jobPostings": postings or [],
        "errorCode": error_code,
    }
    response.raise_for_status.return_value = None
    return response


class TestWorkdayPagination:
    def test_aggregates_multiple_pages(self, scraper: CareerPageScraper) -> None:
        page_one = [
            _workday_posting(f"Intern Role {index}") for index in range(_WORKDAY_PAGE_LIMIT)
        ]
        page_two = [
            _workday_posting(f"Intern Role {index}")
            for index in range(_WORKDAY_PAGE_LIMIT, _WORKDAY_PAGE_LIMIT + 5)
        ]
        responses = [
            _mock_workday_response(status_code=400, postings=[]),
            _mock_workday_response(total=25, postings=page_one),
            _mock_workday_response(total=0, postings=page_two),
        ]

        with patch("scraper.requests.post", side_effect=responses) as mock_post:
            raw = scraper.fetch(WORKDAY_URL)

        assert mock_post.call_count == 3
        payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
        assert payloads[0]["offset"] == 0
        assert payloads[0]["limit"] == _WORKDAY_REQUESTED_PAGE_LIMIT
        assert payloads[1]["offset"] == 0
        assert payloads[1]["limit"] == _WORKDAY_PAGE_LIMIT
        assert payloads[2]["offset"] == _WORKDAY_PAGE_LIMIT
        assert payloads[2]["limit"] == _WORKDAY_PAGE_LIMIT

        data = json.loads(raw or "")
        assert len(data["jobPostings"]) == 25
        assert data["total"] == 25

    def test_stops_on_empty_page(self, scraper: CareerPageScraper) -> None:
        full_page = [
            _workday_posting(f"Intern Role {index}") for index in range(_WORKDAY_PAGE_LIMIT)
        ]
        responses = [
            _mock_workday_response(status_code=400, postings=[]),
            _mock_workday_response(total=40, postings=full_page),
            _mock_workday_response(total=0, postings=[]),
        ]

        with patch("scraper.requests.post", side_effect=responses) as mock_post:
            raw = scraper.fetch(WORKDAY_URL)

        assert mock_post.call_count == 3
        data = json.loads(raw or "")
        assert len(data["jobPostings"]) == _WORKDAY_PAGE_LIMIT

    def test_stops_when_total_reached(self, scraper: CareerPageScraper) -> None:
        page_one = [
            _workday_posting(f"Intern Role {index}") for index in range(_WORKDAY_PAGE_LIMIT)
        ]
        page_two = [_workday_posting("Intern Role 20")]
        responses = [
            _mock_workday_response(status_code=400, postings=[]),
            _mock_workday_response(total=21, postings=page_one),
            _mock_workday_response(total=0, postings=page_two),
            _mock_workday_response(total=21, postings=page_one),
        ]

        with patch("scraper.requests.post", side_effect=responses) as mock_post:
            raw = scraper.fetch(WORKDAY_URL)

        assert mock_post.call_count == 3
        data = json.loads(raw or "")
        assert len(data["jobPostings"]) == 21

    def test_falls_back_to_page_limit_twenty_on_http_400(
        self, scraper: CareerPageScraper
    ) -> None:
        postings = [_workday_posting("Software Engineering Intern")]
        responses = [
            _mock_workday_response(status_code=400, postings=[]),
            _mock_workday_response(total=1, postings=postings),
        ]

        with patch("scraper.requests.post", side_effect=responses) as mock_post:
            raw = scraper.fetch(WORKDAY_URL)

        assert mock_post.call_count == 2
        payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
        assert payloads[0]["limit"] == _WORKDAY_REQUESTED_PAGE_LIMIT
        assert payloads[1]["limit"] == _WORKDAY_PAGE_LIMIT
        assert payloads[1]["offset"] == 0

        data = json.loads(raw or "")
        assert len(data["jobPostings"]) == 1

    def test_extract_text_includes_all_paginated_jobs(
        self, scraper: CareerPageScraper
    ) -> None:
        aggregated = {
            "total": 2,
            "jobPostings": [
                _workday_posting("Software Engineering Intern", "Seattle, WA"),
                _workday_posting("Data Science Intern", "Austin, TX"),
            ],
        }

        text = scraper.extract_text(json.dumps(aggregated), WORKDAY_URL)

        assert "software engineering intern" in text
        assert "data science intern" in text
        assert "seattle, wa" in text
        assert "austin, tx" in text
