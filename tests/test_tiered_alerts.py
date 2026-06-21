"""Tests for tier-based alert channel routing."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from alerts import AlertManager
from config import Settings
from models import AlertPayload


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
    return AlertManager(_test_settings())


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


class TestFireTierRouting:
    def test_standard_tier_sends_push_only(
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
        sms.assert_not_called()
        call.assert_not_called()
        email.assert_not_called()
        assert results == {
            "sms": False,
            "call": False,
            "push": True,
            "email": False,
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
