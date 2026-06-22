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
        "gmail_address": "test@example.com",
        "gmail_app_password": "test_password",
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
        assert f"Apply: {expected_url}" in body

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
        assert "Apply: https://boards.greenhouse.io/skydio/jobs/456" in body
        assert headers["Title"] == "Skydio - Computer Vision Intern - Perception"


class TestFireTierRouting:
    def test_standard_tier_sends_push_and_email(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        payload = replace(sample_payload, tier="standard")

        with (
            patch.object(manager, "send_push", return_value=True) as push,
            patch.object(manager, "send_sms", return_value=True) as sms,
            patch.object(manager, "send_voice_call", return_value=True) as call,
            patch.object(manager, "send_email", return_value=True) as email,
        ):
            results = manager.fire(payload)

        push.assert_called_once_with(payload)
        email.assert_called_once_with(payload)
        sms.assert_not_called()
        call.assert_not_called()
        assert results == {
            "sms": False,
            "call": False,
            "push": True,
            "email": True,
        }

    def test_high_tier_sends_all_channels(
        self, manager: AlertManager, sample_payload: AlertPayload
    ) -> None:
        payload = replace(sample_payload, tier="high")

        with (
            patch.object(manager, "send_push", return_value=True) as push,
            patch.object(manager, "send_sms", return_value=True) as sms,
            patch.object(manager, "send_voice_call", return_value=True) as call,
            patch.object(manager, "send_email", return_value=True) as email,
        ):
            results = manager.fire(payload)

        push.assert_called_once_with(payload)
        sms.assert_called_once_with(payload)
        call.assert_called_once_with(payload)
        email.assert_called_once_with(payload)
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
            patch.object(manager, "send_push", return_value=True),
            patch.object(manager, "send_sms", return_value=False),
            patch.object(manager, "send_voice_call", return_value=True),
            patch.object(manager, "send_email", return_value=False),
        ):
            results = manager.fire(payload)

        assert results["push"] is True
        assert results["call"] is True
        assert results["sms"] is False
        assert results["email"] is False
