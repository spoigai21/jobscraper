"""Tests for CareerPageScraper."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from config import Settings
from models import AlertPayload, CompanyConfig, StateRecord
from scraper import CareerPageScraper


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
        keywords=["intern", "2027"],
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
        text = "we are hiring summer interns for 2027 roles"
        keywords = ["INTERN", "2027", "internship"]

        assert scraper.check_keywords(text, keywords) == "INTERN"

    def test_returns_none_when_no_match(self, scraper: CareerPageScraper) -> None:
        assert scraper.check_keywords("full-time engineer", ["intern", "2027"]) is None


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

        assert result is None
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

        assert result is None
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

        assert isinstance(result, AlertPayload)
        assert result.company == "TestCo"
        assert result.url == company.url
        assert result.trigger_keyword == "intern"
        assert result.diff_snippet.startswith("New: ")
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

        assert result is None
        assert state.alert_count == 0

    def test_first_poll_with_empty_previous_hash(
        self, scraper: CareerPageScraper, company: CompanyConfig
    ) -> None:
        html = _sample_html("summer intern 2027 program")
        state = self._state(last_hash="")
        expected_text = scraper.extract_text(html)

        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.poll_company(company, state)

        assert result is None
        assert state.last_hash == scraper.hash_content(expected_text)
        assert state.last_text == expected_text
        assert state.alert_count == 0
