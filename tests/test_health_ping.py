"""Tests for periodic health ping notifications."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from monitor.app import (
    _maybe_send_health_ping,
    run_poll_cycle,
)
from monitor.config import Settings
from monitor.models import CompanyConfig, PollResult, StateRecord


def _settings(**overrides: object) -> Settings:
    defaults = {
        "twilio_account_sid": "",
        "twilio_auth_token": "",
        "twilio_from_number": "",
        "twilio_to_number": "",
        "ntfy_topic": "test-topic",
        "alert_email_to": "",
        "health_ping_enabled": True,
        "health_ping_interval_seconds": 86400,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture(autouse=True)
def _reset_health_ping_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import monitor.app as app_module

    monkeypatch.setattr(app_module, "_last_health_ping_at", None)
    monkeypatch.setattr(app_module, "_poll_cycles_since_last_ping", 0)
    monkeypatch.setattr(app_module, "_last_cycle_companies_checked", 0)
    monkeypatch.setattr(app_module, "_last_successful_poll_at", None)


class TestMaybeSendHealthPing:
    def test_sends_when_interval_elapsed_and_cycle_completed(self) -> None:
        import monitor.app as app_module

        app_module._poll_cycles_since_last_ping = 2
        app_module._last_cycle_companies_checked = 5
        app_module._last_successful_poll_at = datetime.now(timezone.utc)
        app_module._last_health_ping_at = datetime.now(timezone.utc) - timedelta(
            seconds=90000
        )

        alert_manager = MagicMock()
        alert_manager.send_health_ping.return_value = True

        _maybe_send_health_ping(alert_manager, _settings())

        alert_manager.send_health_ping.assert_called_once()
        kwargs = alert_manager.send_health_ping.call_args.kwargs
        assert kwargs["companies_checked"] == 5
        assert kwargs["last_poll_at"] is not None
        assert app_module._poll_cycles_since_last_ping == 0
        assert app_module._last_health_ping_at is not None

    def test_skips_when_disabled(self) -> None:
        import monitor.app as app_module

        app_module._poll_cycles_since_last_ping = 1
        alert_manager = MagicMock()

        _maybe_send_health_ping(
            alert_manager,
            _settings(health_ping_enabled=False),
        )

        alert_manager.send_health_ping.assert_not_called()

    def test_skips_before_first_completed_cycle(self) -> None:
        alert_manager = MagicMock()

        _maybe_send_health_ping(alert_manager, _settings())

        alert_manager.send_health_ping.assert_not_called()

    def test_skips_when_interval_not_elapsed(self) -> None:
        import monitor.app as app_module

        app_module._poll_cycles_since_last_ping = 1
        app_module._last_health_ping_at = datetime.now(timezone.utc) - timedelta(
            seconds=60
        )

        alert_manager = MagicMock()

        _maybe_send_health_ping(alert_manager, _settings())

        alert_manager.send_health_ping.assert_not_called()


class TestRunPollCycleHealthPing:
    def test_increments_cycle_counter_after_successful_poll(self) -> None:
        import monitor.app as app_module

        company = CompanyConfig(
            name="Waymo",
            url="https://example.com/jobs",
            keywords=["intern"],
            enabled=True,
        )
        state = StateRecord(
            company="Waymo",
            url=company.url,
            last_hash="",
            last_checked="",
            last_alerted=None,
            alert_count=0,
        )

        store = MagicMock()
        store.get_state.return_value = state
        scraper = MagicMock()
        scraper.poll_company.return_value = PollResult()
        alert_manager = MagicMock()
        alert_manager.send_health_ping.return_value = False

        with patch.object(app_module, "_maybe_send_health_ping") as maybe_ping:
            run_poll_cycle(
                scraper,
                store,
                alert_manager,
                [company],
                _settings(health_ping_interval_seconds=86400),
            )
            maybe_ping.assert_called_once()

        assert app_module._poll_cycles_since_last_ping == 1
        assert app_module._last_cycle_companies_checked == 1
