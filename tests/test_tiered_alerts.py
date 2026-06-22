"""Tests for tier-based alert channel routing."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from monitor.alerts import AlertManager
from monitor.config import Settings
from monitor.models import AlertPayload
from monitor.profile import load_profile


def _test_settings(**overrides: object) -> Settings:
    defaults = {
        "twilio_account_sid": "test_sid",
        "twilio_auth_token": "test_token",
        "twilio_from_number": "+15550001001",
        "twilio_to_number": "+15550001002",
        "ntfy_topic": "test-topic",
        "ntfy_token": "tk_test_token",
        "alert_email_to": "test@example.com",
        "min_alert_interval": 3600,
        "request_timeout": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def manager() -> AlertManager:
    return AlertManager(_test_settings(), load_profile())


@pytest.fixture
def sample_payload() -> AlertPayload:
    return AlertPayload(
        company="Skydio",
        url="https://boards.greenhouse.io/skydio/jobs/123",
        trigger_keyword="intern",
        detected_at="2027-01-15T12:00:00+00:00",
        diff_snippet="New: Computer Vision Intern (Perception)",
        job_title="Computer Vision Intern — Perception",
        job_url="https://boards.greenhouse.io/skydio/jobs/123",
        relevance_score=11,
        tier="standard",
        notification_keywords=("intern", "summer 2027", "Python", "OpenCV"),
    )


class TestVoiceDatetime:
    def test_formats_iso_timestamp_for_speech(self) -> None:
        assert (
            AlertManager._format_voice_datetime("2027-01-16T02:34:00+00:00")
            == "January 15th, 9:34 PM EST"
        )
        assert (
            AlertManager._format_voice_datetime("2027-06-21T01:34:00+00:00")
            == "June 20th, 9:34 PM EDT"
        )

    def test_returns_original_on_invalid_timestamp(self) -> None:
        assert AlertManager._format_voice_datetime("not-a-date") == "not-a-date"


class TestPushNotificationContent:
    def test_push_body_format(self, manager: AlertManager, sample_payload: AlertPayload) -> None:
        body = manager._push_body(sample_payload)
        expected = (
            "Keywords detected: intern, summer 2027, Python, OpenCV\n"
            "Application: https://boards.greenhouse.io/skydio/jobs/123"
        )
        assert body == expected

    def test_push_title_uses_company_and_role(self, manager: AlertManager, sample_payload: AlertPayload) -> None:
        assert (
            manager._push_title(sample_payload)
            == "Skydio - Computer Vision Intern - Perception"
        )

    def test_push_title_high_tier_no_prefix(self, manager: AlertManager, sample_payload: AlertPayload) -> None:
        payload = replace(sample_payload, tier="high")
        assert (
            manager._push_title(payload)
            == "Skydio - Computer Vision Intern - Perception"
        )

    @pytest.mark.parametrize(
        ("job_url", "company_url", "expected_url"),
        [
            (
                "https://boards.greenhouse.io/skydio/jobs/123",
                "https://boards.greenhouse.io/skydio",
                "https://boards.greenhouse.io/skydio/jobs/123",
            ),
            (
                "https://jobs.ashbyhq.com/skydio/abc-123",
                "https://api.ashbyhq.com/posting-api/job-board/skydio",
                "https://jobs.ashbyhq.com/skydio/abc-123",
            ),
            (
                "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Intern_123",
                "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs",
                "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Intern_123",
            ),
            (
                "",
                "https://example.com/careers",
                "https://example.com/careers",
            ),
        ],
    )
    def test_push_body_includes_apply_url_for_board_types(
        self,
        manager: AlertManager,
        sample_payload: AlertPayload,
        job_url: str,
        company_url: str,
        expected_url: str,
    ) -> None:
        payload = replace(
            sample_payload,
            job_url=job_url,
            url=company_url if not job_url else job_url,
        )
        body = manager._push_body(payload)
        assert f"Application: {expected_url}" in body

    def test_push_body_html_fallback_uses_diff_snippet_title(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        payload = replace(
            sample_payload,
            job_title="",
            job_url="",
            url="https://example.com/careers",
            diff_snippet="New: Software Engineering Intern (Remote)",
            notification_keywords=("internship", "undergrad"),
        )
        body = manager._push_body(payload)
        assert body.startswith("Keywords detected: internship, undergrad")
        assert manager._push_title(payload) == "Skydio - Software Engineering Intern"
        assert "Application: https://example.com/careers" in body

    @patch("monitor.alerts.requests.post")
    def test_send_push_includes_url_in_body_and_click_header(
        self,
        mock_post,
        manager: AlertManager,
        sample_payload: AlertPayload,
    ) -> None:
        mock_post.return_value.raise_for_status = lambda: None
        payload = replace(
            sample_payload,
            job_url="https://boards.greenhouse.io/skydio/jobs/456",
            url="https://boards.greenhouse.io/skydio/jobs/456",
        )

        assert manager.send_push(payload) is True

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        headers = kwargs["headers"]
        body = kwargs["data"].decode("utf-8")
        assert headers["Click"] == "https://boards.greenhouse.io/skydio/jobs/456"
        assert "Application: https://boards.greenhouse.io/skydio/jobs/456" in body
        assert headers["Title"] == "Skydio - Computer Vision Intern - Perception"
        assert "Markdown" not in headers
        assert "Tags" not in headers


class TestEmailNotificationContent:
    def test_email_body_format(self, manager: AlertManager, sample_payload: AlertPayload) -> None:
        body = manager._email_body(sample_payload)
        expected = (
            "Skydio - Computer Vision Intern - Perception\n"
            "\n"
            "Tier: standard\n"
            "Priority score: 11\n"
            "\n"
            "Keywords detected: intern, summer 2027, Python, OpenCV\n"
            "Application: https://boards.greenhouse.io/skydio/jobs/123\n"
            "Detected: January 15th, 7:00 AM EST\n"
            "\n"
            "New: Computer Vision Intern (Perception)\n"
            "\n"
            "Sent by your internship monitor"
        )
        assert body == expected

    def test_email_subject_matches_push_title(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        assert (
            manager._email_subject(sample_payload)
            == "Skydio - Computer Vision Intern - Perception"
        )

    def test_email_subject_high_tier_no_prefix(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        payload = replace(sample_payload, tier="high")
        assert (
            manager._email_subject(payload)
            == "Skydio - Computer Vision Intern - Perception"
        )

    def test_email_body_omits_priority_score_when_zero(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        payload = replace(sample_payload, relevance_score=0)
        body = manager._email_body(payload)
        assert "Priority score" not in body
        assert "Tier: standard" in body

    @patch("monitor.alerts.requests.post")
    def test_send_email_uses_ntfy_when_topic_configured(
        self,
        mock_post,
        manager: AlertManager,
        sample_payload: AlertPayload,
    ) -> None:
        mock_post.return_value.ok = True

        assert manager.send_email(sample_payload) is True

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer tk_test_token"
        assert call_kwargs["headers"]["Email"] == "test@example.com"
        assert call_kwargs["headers"]["Title"] == "Skydio - Computer Vision Intern - Perception"
        body = call_kwargs["data"].decode("utf-8")
        assert "Keywords detected: intern, summer 2027, Python, OpenCV" in body
        assert "Application: https://boards.greenhouse.io/skydio/jobs/123" in body
        assert "Priority score: 11" in body
        assert "Tier: standard" in body
        assert "Detected: January 15th, 7:00 AM EST" in body


class TestFireTierRouting:
    def test_standard_tier_sends_push_and_email(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        payload = replace(sample_payload, tier="standard")

        with (
            patch.object(
                manager, "send_push_and_email_ntfy", return_value=(True, True)
            ) as combined,
            patch.object(manager, "send_push") as push,
            patch.object(manager, "send_sms") as sms,
            patch.object(manager, "send_voice_call") as call,
            patch.object(manager, "send_email") as email,
        ):
            results = manager.fire(payload)

        combined.assert_called_once_with(payload)
        push.assert_not_called()
        email.assert_not_called()
        sms.assert_not_called()
        call.assert_not_called()
        assert results == {
            "sms": False,
            "call": False,
            "push": True,
            "email": True,
        }

    def test_standard_tier_without_ntfy_token_uses_separate_channels(
        self, sample_payload: AlertPayload
    ) -> None:
        manager = AlertManager(_test_settings(ntfy_token=""), load_profile())
        payload = replace(sample_payload, tier="standard")

        with (
            patch.object(manager, "send_push", return_value=True) as push,
            patch.object(manager, "send_email", return_value=True) as email,
            patch.object(manager, "send_push_and_email_ntfy") as combined,
        ):
            results = manager.fire(payload)

        push.assert_called_once_with(payload)
        email.assert_called_once_with(payload)
        combined.assert_not_called()
        assert results["push"] is True
        assert results["email"] is True

    @patch("monitor.alerts.requests.post")
    def test_combined_ntfy_sends_one_request(
        self,
        mock_post,
        manager: AlertManager,
        sample_payload: AlertPayload,
    ) -> None:
        mock_post.return_value.ok = True

        push_ok, email_ok = manager.send_push_and_email_ntfy(sample_payload)

        assert push_ok is True
        assert email_ok is True
        mock_post.assert_called_once()
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Email"] == "test@example.com"
        assert headers["Authorization"] == "Bearer tk_test_token"

    def test_high_tier_sends_all_channels(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        payload = replace(sample_payload, tier="high")

        with (
            patch.object(
                manager, "send_push_and_email_ntfy", return_value=(True, True)
            ) as combined,
            patch.object(manager, "send_push") as push,
            patch.object(manager, "send_sms", return_value=True) as sms,
            patch.object(manager, "send_voice_call", return_value=True) as call,
            patch.object(manager, "send_email") as email,
        ):
            results = manager.fire(payload)

        combined.assert_called_once_with(payload)
        push.assert_not_called()
        email.assert_not_called()
        sms.assert_called_once_with(payload)
        call.assert_called_once_with(payload)
        assert results == {
            "sms": True,
            "call": True,
            "push": True,
            "email": True,
        }

    def test_high_tier_reports_partial_failures(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        payload = replace(sample_payload, tier="high")

        with (
            patch.object(
                manager, "send_push_and_email_ntfy", return_value=(True, False)
            ),
            patch.object(manager, "send_sms", return_value=False),
            patch.object(manager, "send_voice_call", return_value=True),
        ):
            results = manager.fire(payload)

        assert results["push"] is True
        assert results["call"] is True
        assert results["sms"] is False
        assert results["email"] is False
