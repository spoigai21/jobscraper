"""Tests for CareerPageScraper."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from monitor.config import EIGHTFOLD_MAX_PAGES, EIGHTFOLD_PAGE_DELAY_SECONDS, Settings
from monitor.models import AlertPayload, CompanyConfig, StateRecord
from monitor.profile import load_profile
from monitor.scraper import CareerPageScraper, _WORKDAY_PAGE_LIMIT, _WORKDAY_REQUESTED_PAGE_LIMIT


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
        assert payload.pending_hash
        assert state.alert_count == 2
        assert state.last_hash == "stale-hash"

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
        assert state.last_hash == "stale-hash"
        assert state.last_text == "legacy staff engineer listings only"

    def test_html_cooldown_preserves_hash_then_alerts_after_interval(
        self, scraper: CareerPageScraper, company: CompanyConfig
    ) -> None:
        html = _sample_html("new summer intern 2027 opening posted today")
        cooldown_state = self._state(
            last_hash="stale-hash",
            last_text="legacy staff engineer listings only",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=100)
            ).isoformat(),
        )

        with patch.object(scraper, "fetch", return_value=html):
            blocked = scraper.poll_company(company, cooldown_state)

        assert blocked == []
        assert cooldown_state.last_hash == "stale-hash"

        ready_state = self._state(
            last_hash="stale-hash",
            last_text="legacy staff engineer listings only",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
        )

        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.poll_company(company, ready_state)

        assert len(result) == 1
        assert result[0].pending_hash

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


LEVER_HTML_PAGE = """
<html><body>
  <div class="posting" data-qa-posting-id="lever-1">
    <a href="https://jobs.lever.co/palantir/lever-1" class="posting-title">
      <h5>Software Engineering Intern - Summer 2027</h5>
    </a>
    <div class="posting-categories">
      <span>Engineering</span>
      <span>Denver, CO</span>
      <span>Internship</span>
    </div>
    <div class="posting-description">
      Build services with Python and FastAPI for perception pipelines.
    </div>
  </div>
</body></html>
"""


class TestPollHtmlJobs:
    @pytest.fixture
    def lever_company(self) -> CompanyConfig:
        return CompanyConfig(
            name="Palantir",
            url="https://jobs.lever.co/palantir?commitment=Internship",
            keywords=["intern", "summer 2027", "internship"],
            enabled=True,
        )

    @pytest.fixture
    def profiled_scraper(self) -> CareerPageScraper:
        return CareerPageScraper(_test_settings(), load_profile())

    def test_first_poll_seeds_html_job_ids(
        self,
        profiled_scraper: CareerPageScraper,
        lever_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Palantir",
            url=lever_company.url,
            last_hash="",
            last_checked="",
            last_alerted=None,
            alert_count=0,
        )

        with patch.object(profiled_scraper, "fetch", return_value=LEVER_HTML_PAGE):
            result = profiled_scraper.poll_company(lever_company, state)

        assert result == []
        assert json.loads(state.seen_job_ids) == ["lever-1"]

    def test_new_html_job_emits_notification_keywords(
        self,
        profiled_scraper: CareerPageScraper,
        lever_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Palantir",
            url=lever_company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["old-id"]',
        )

        with patch.object(profiled_scraper, "fetch", return_value=LEVER_HTML_PAGE):
            result = profiled_scraper.poll_company(lever_company, state)

        assert len(result) == 1
        payload = result[0]
        assert payload.job_title == "Software Engineering Intern - Summer 2027"
        assert payload.trigger_keyword in {"intern", "summer 2027", "internship"}
        assert payload.notification_keywords
        lowered = {term.lower() for term in payload.notification_keywords}
        assert "python" in lowered or "fastapi" in lowered


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
        assert payload.job_id == "501"
        assert json.loads(state.seen_job_ids) == ["999"]

    def test_cooldown_does_not_consume_new_job_id(
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
                datetime.now(timezone.utc) - timedelta(seconds=100)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["999"]',
        )

        with patch.object(profiled_scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            blocked = profiled_scraper.poll_company(greenhouse_company, state)

        assert blocked == []
        assert json.loads(state.seen_job_ids) == ["999"]

        state.last_alerted = (
            datetime.now(timezone.utc) - timedelta(seconds=7200)
        ).isoformat()

        with patch.object(profiled_scraper, "fetch", return_value=GREENHOUSE_BOARD_JSON):
            result = profiled_scraper.poll_company(greenhouse_company, state)

        assert len(result) == 1
        assert result[0].job_id == "501"
        assert json.loads(state.seen_job_ids) == ["999"]


WORKDAY_BOARD_JSON = json.dumps(
    {
        "total": 2,
        "jobPostings": [
            {
                "title": "Software Engineering Intern Summer 2027",
                "externalPath": "/job/California/Software-Engineering-Intern_JR501",
                "locationsText": "California - San Francisco",
                "bulletFields": ["JR501"],
            },
            {
                "title": "Project Lead, Partnerships",
                "externalPath": "/job/California/Project-Lead_JR999",
                "locationsText": "California - San Francisco",
                "bulletFields": ["JR999"],
            },
        ],
    }
)


class TestPollWorkdayBoard:
    @pytest.fixture
    def workday_company(self) -> CompanyConfig:
        return CompanyConfig(
            name="Salesforce",
            url=(
                "https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/"
                "External_Career_Site/jobs?searchText=internship"
            ),
            keywords=["intern", "internship"],
            enabled=True,
        )

    @pytest.fixture
    def profiled_scraper(self) -> CareerPageScraper:
        return CareerPageScraper(_test_settings(), load_profile())

    def test_first_poll_seeds_workday_job_ids_without_alert(
        self,
        profiled_scraper: CareerPageScraper,
        workday_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Salesforce",
            url=workday_company.url,
            last_hash="",
            last_checked="",
            last_alerted=None,
            alert_count=0,
        )

        with patch.object(profiled_scraper, "fetch", return_value=WORKDAY_BOARD_JSON):
            result = profiled_scraper.poll_company(workday_company, state)

        assert result == []
        assert set(json.loads(state.seen_job_ids)) == {"JR501", "JR999"}

    def test_new_workday_intern_emits_scored_alert(
        self,
        profiled_scraper: CareerPageScraper,
        workday_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Salesforce",
            url=workday_company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["JR999"]',
        )

        with patch.object(profiled_scraper, "fetch", return_value=WORKDAY_BOARD_JSON):
            result = profiled_scraper.poll_company(workday_company, state)

        assert len(result) == 1
        assert result[0].job_title == "Software Engineering Intern Summer 2027"

    def test_non_intern_workday_job_rotation_does_not_alert(
        self,
        profiled_scraper: CareerPageScraper,
        workday_company: CompanyConfig,
    ) -> None:
        rotated = json.dumps(
            {
                "total": 2,
                "jobPostings": [
                    {
                        "title": "Software Engineering Intern Summer 2027",
                        "externalPath": "/job/California/Software-Engineering-Intern_JR501",
                        "locationsText": "California - San Francisco",
                        "bulletFields": ["JR501"],
                    },
                    {
                        "title": "Director, Enterprise Sales",
                        "externalPath": "/job/California/Director-Enterprise-Sales_JR777",
                        "locationsText": "California - San Francisco",
                        "bulletFields": ["JR777"],
                    },
                ],
            }
        )
        state = StateRecord(
            company="Salesforce",
            url=workday_company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["JR501", "JR999"]',
        )

        with patch.object(profiled_scraper, "fetch", return_value=rotated):
            result = profiled_scraper.poll_company(workday_company, state)

        assert result == []
        assert set(json.loads(state.seen_job_ids)) == {"JR501", "JR777", "JR999"}


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

        with patch("monitor.scraper.requests.post", side_effect=responses) as mock_post:
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

    def test_retries_empty_page_when_under_total(
        self, scraper: CareerPageScraper
    ) -> None:
        page_one = [
            _workday_posting(f"Intern Role {index}") for index in range(_WORKDAY_PAGE_LIMIT)
        ]
        page_two = [
            _workday_posting(f"Intern Role {index}")
            for index in range(_WORKDAY_PAGE_LIMIT, _WORKDAY_PAGE_LIMIT * 2)
        ]
        responses = [
            _mock_workday_response(status_code=400, postings=[]),
            _mock_workday_response(total=40, postings=page_one),
            _mock_workday_response(total=0, postings=[]),
            _mock_workday_response(total=0, postings=page_two),
        ]

        with patch("monitor.scraper.requests.post", side_effect=responses) as mock_post:
            raw = scraper.fetch(WORKDAY_URL)

        assert mock_post.call_count == 4
        payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
        assert payloads[2]["offset"] == _WORKDAY_PAGE_LIMIT
        assert payloads[3]["offset"] == _WORKDAY_PAGE_LIMIT

        data = json.loads(raw or "")
        assert len(data["jobPostings"]) == _WORKDAY_PAGE_LIMIT * 2
        assert data["total"] == 40

    def test_stops_on_empty_page_when_total_unknown(
        self, scraper: CareerPageScraper
    ) -> None:
        full_page = [
            _workday_posting(f"Intern Role {index}") for index in range(_WORKDAY_PAGE_LIMIT)
        ]
        responses = [
            _mock_workday_response(status_code=400, postings=[]),
            _mock_workday_response(total=None, postings=full_page),
            _mock_workday_response(total=0, postings=[]),
        ]

        with patch("monitor.scraper.requests.post", side_effect=responses) as mock_post:
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

        with patch("monitor.scraper.requests.post", side_effect=responses) as mock_post:
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

        with patch("monitor.scraper.requests.post", side_effect=responses) as mock_post:
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


MICROSOFT_URL = (
    "https://apply.careers.microsoft.com/api/pcsx/search"
    "?domain=microsoft.com&query=intern"
)

MICROSOFT_BOARD_JSON = json.dumps(
    {
        "positions": [
            {
                "id": 1970393556864498,
                "name": "Software Engineering Intern - AI Frontiers",
                "department": "Applied Sciences",
                "locations": ["United States, Washington, Redmond"],
                "positionUrl": "/careers/job/1970393556864498",
            },
            {
                "id": 1970393556862611,
                "name": "Business Program Management - Intern Opportunities",
                "department": "Business Program Management",
                "locations": ["Brazil, São Paulo, São Paulo"],
                "positionUrl": "/careers/job/1970393556862611",
            },
        ],
        "count": 2,
    }
)


def _microsoft_position(position_id: int, title: str) -> dict[str, object]:
    return {
        "id": position_id,
        "name": title,
        "department": "Engineering",
        "locations": ["Redmond, WA"],
        "positionUrl": f"/careers/job/{position_id}",
    }


def _mock_microsoft_response(*, count: int, positions: list[dict[str, object]]) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "status": 200,
        "data": {"positions": positions, "count": count},
    }
    return response


def _mock_microsoft_rate_limit(*, retry_after: str | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = 429
    response.headers = {"Retry-After": retry_after} if retry_after else {}
    return response


class TestFetchMicrosoft:
    @pytest.fixture
    def scraper(self) -> CareerPageScraper:
        return CareerPageScraper(_test_settings())

    def test_paginates_until_count_reached(self, scraper: CareerPageScraper) -> None:
        page_one = [
            _microsoft_position(1000 + index, f"Intern Role {index}")
            for index in range(10)
        ]
        page_two = [
            _microsoft_position(2000 + index, f"Intern Role {10 + index}")
            for index in range(5)
        ]

        with patch(
            "monitor.scraper.requests.get",
            side_effect=[
                _mock_microsoft_response(count=15, positions=page_one),
                _mock_microsoft_response(count=15, positions=page_two),
            ],
        ) as mock_get:
            raw = scraper.fetch(MICROSOFT_URL)

        assert mock_get.call_count == 2
        payload = json.loads(raw)
        assert len(payload["positions"]) == 15
        assert payload["count"] == 15

    def test_caps_pagination_at_five_pages(self, scraper: CareerPageScraper) -> None:
        pages = [
            _mock_microsoft_response(
                count=100,
                positions=[
                    _microsoft_position(page * 10 + index, f"Role {page * 10 + index}")
                    for index in range(10)
                ],
            )
            for page in range(6)
        ]

        with patch("monitor.scraper.requests.get", side_effect=pages) as mock_get:
            raw = scraper.fetch(MICROSOFT_URL)

        assert mock_get.call_count == EIGHTFOLD_MAX_PAGES
        payload = json.loads(raw)
        assert len(payload["positions"]) == EIGHTFOLD_MAX_PAGES * 10

    def test_retries_single_page_on_429_without_restarting(self, scraper: CareerPageScraper) -> None:
        page_one = [
            _microsoft_position(1000 + index, f"Intern Role {index}")
            for index in range(10)
        ]
        page_two = [
            _microsoft_position(2000 + index, f"Intern Role {10 + index}")
            for index in range(5)
        ]

        with patch(
            "monitor.scraper.requests.get",
            side_effect=[
                _mock_microsoft_response(count=15, positions=page_one),
                _mock_microsoft_rate_limit(retry_after="0"),
                _mock_microsoft_response(count=15, positions=page_two),
            ],
        ) as mock_get, patch("monitor.scraper.time.sleep") as mock_sleep:
            raw = scraper.fetch(MICROSOFT_URL)

        assert mock_get.call_count == 3
        mock_sleep.assert_any_call(0.0)
        payload = json.loads(raw)
        assert len(payload["positions"]) == 15

    def test_rate_limit_exhaustion_returns_none(self, scraper: CareerPageScraper) -> None:
        with patch(
            "monitor.scraper.requests.get",
            return_value=_mock_microsoft_rate_limit(),
        ), patch("monitor.scraper.time.sleep"):
            raw = scraper.fetch(MICROSOFT_URL)

        assert raw is None
        assert scraper._fetch_failure_reason == "rate_limited"

    def test_uses_eightfold_page_delay_between_pages(
        self, scraper: CareerPageScraper
    ) -> None:
        page_one = [
            _microsoft_position(1000 + index, f"Intern Role {index}")
            for index in range(10)
        ]
        page_two = [
            _microsoft_position(2000 + index, f"Intern Role {10 + index}")
            for index in range(5)
        ]

        with patch(
            "monitor.scraper.requests.get",
            side_effect=[
                _mock_microsoft_response(count=15, positions=page_one),
                _mock_microsoft_response(count=15, positions=page_two),
            ],
        ), patch("monitor.scraper.time.sleep") as mock_sleep:
            scraper.fetch(MICROSOFT_URL)

        mock_sleep.assert_called_once_with(EIGHTFOLD_PAGE_DELAY_SECONDS)

    def test_extract_text_from_microsoft_json(self, scraper: CareerPageScraper) -> None:
        text = scraper.extract_text(MICROSOFT_BOARD_JSON, MICROSOFT_URL)
        assert "software engineering intern - ai frontiers" in text
        assert "applied sciences" in text


class TestPollMicrosoftBoard:
    @pytest.fixture
    def microsoft_company(self) -> CompanyConfig:
        return CompanyConfig(
            name="Microsoft",
            url=MICROSOFT_URL,
            keywords=["internship", "engineering intern", "summer 2027"],
            enabled=True,
        )

    @pytest.fixture
    def profiled_scraper(self) -> CareerPageScraper:
        return CareerPageScraper(_test_settings(), load_profile())

    def test_first_poll_seeds_microsoft_job_ids_without_alert(
        self,
        profiled_scraper: CareerPageScraper,
        microsoft_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Microsoft",
            url=microsoft_company.url,
            last_hash="",
            last_checked="",
            last_alerted=None,
            alert_count=0,
        )

        with patch.object(
            profiled_scraper, "fetch", return_value=MICROSOFT_BOARD_JSON
        ):
            result = profiled_scraper.poll_company(microsoft_company, state)

        assert result == []
        assert set(json.loads(state.seen_job_ids)) == {
            "1970393556864498",
            "1970393556862611",
        }

    def test_new_microsoft_intern_emits_scored_alert(
        self,
        profiled_scraper: CareerPageScraper,
        microsoft_company: CompanyConfig,
    ) -> None:
        state = StateRecord(
            company="Microsoft",
            url=microsoft_company.url,
            last_hash="seeded",
            last_checked="",
            last_alerted=(
                datetime.now(timezone.utc) - timedelta(seconds=7200)
            ).isoformat(),
            alert_count=0,
            seen_job_ids='["1970393556862611"]',
        )

        with patch.object(
            profiled_scraper, "fetch", return_value=MICROSOFT_BOARD_JSON
        ):
            result = profiled_scraper.poll_company(microsoft_company, state)

        assert len(result) == 1
        assert result[0].job_title == "Software Engineering Intern - AI Frontiers"
