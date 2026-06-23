"""Tests for AlertManager health ping delivery."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from monitor.alerts import AlertManager
from monitor.config import Settings


def _settings(**overrides: object) -> Settings:
    defaults = {
        "twilio_account_sid": "",
        "twilio_auth_token": "",
        "twilio_from_number": "",
        "twilio_to_number": "",
        "ntfy_topic": "test-topic",
        "alert_email_to": "",
        "request_timeout": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestSendHealthPing:
    def test_posts_low_priority_ntfy_message(self) -> None:
        manager = AlertManager(_settings())
        response = MagicMock()
        response.ok = True

        with patch("monitor.alerts.requests.post", return_value=response) as post:
            ok = manager.send_health_ping(
                uptime_hours=12.5,
                companies_checked=8,
                last_poll_at="2026-06-22T12:00:00+00:00",
            )

        assert ok is True
        post.assert_called_once()
        args, kwargs = post.call_args
        assert args[0] == "https://ntfy.sh/test-topic"
        assert kwargs["headers"]["Priority"] == "low"
        assert "Uptime: 12.5 hours" in kwargs["data"].decode("utf-8")
        assert "Companies checked (last cycle): 8" in kwargs["data"].decode("utf-8")

    def test_skips_when_ntfy_topic_missing(self) -> None:
        manager = AlertManager(_settings(ntfy_topic=""))
        assert manager.send_health_ping(
            uptime_hours=1.0,
            companies_checked=1,
            last_poll_at=None,
        ) is False
