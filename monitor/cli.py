"""Command-line interface for the internship monitor."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import click

from monitor.alerts import AlertManager
from monitor.companies import COMPANIES
from monitor.config import PACKAGE_DIR, Settings, get_settings, setup_logging
from monitor.app import get_poll_interval, main as run_monitor
from monitor.models import AlertPayload, CompanyConfig, StateRecord
from monitor.profile import load_profile
from monitor.storage import StateStore

COMPANIES_PATH = PACKAGE_DIR / "companies.py"
PACIFIC = ZoneInfo("America/Los_Angeles")

STATUS_OK = "OK"
STATUS_CHANGED = "CHANGED"
STATUS_ERROR = "ERROR"

CHANNELS = ("sms", "call", "push", "email")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: str | None) -> str:
    parsed = _parse_iso(value)
    if parsed is None:
        return "-"
    return parsed.astimezone(PACIFIC).strftime("%Y-%m-%d %H:%M %Z")


def _company_status(
    company: CompanyConfig,
    state: StateRecord | None,
    settings: Settings,
) -> str:
    if state is None or not state.last_checked.strip():
        return STATUS_ERROR

    last_checked = _parse_iso(state.last_checked)
    if last_checked is None:
        return STATUS_ERROR

    now = datetime.now(timezone.utc)
    if (now - last_checked).total_seconds() > get_poll_interval(settings) * 2:
        return STATUS_ERROR

    if state.last_hash.strip() and state.last_alerted:
        last_alerted = _parse_iso(state.last_alerted)
        if last_alerted is not None:
            if (now - last_alerted).total_seconds() <= settings.min_alert_interval:
                return STATUS_CHANGED

    return STATUS_OK


def _toggle_company_enabled(company_name: str) -> bool:
    content = COMPANIES_PATH.read_text(encoding="utf-8")
    pattern = (
        rf'(CompanyConfig\(\s*name="{re.escape(company_name)}"[\s\S]*?enabled=)'
        r"(True|False)"
    )
    match = re.search(pattern, content)
    if match is None:
        raise click.ClickException(
            f'Company "{company_name}" not found in companies.py. '
            "Use an exact name from the status output."
        )

    current = match.group(2) == "True"
    new_value = "False" if current else "True"
    updated = content[: match.start(2)] + new_value + content[match.end(2) :]
    COMPANIES_PATH.write_text(updated, encoding="utf-8")
    return new_value == "True"


@click.group()
def cli() -> None:
    """Internship monitor command-line tools."""


@cli.command()
def status() -> None:
    """Show monitoring status for all configured companies."""
    setup_logging()
    settings = get_settings()
    store = StateStore()
    states = {record.company: record for record in store.get_all_states()}
    poll_interval = get_poll_interval(settings)

    click.echo(
        f"{'Company':<20} {'En':>3} {'Last Checked':<22} "
        f"{'Last Alerted':<22} {'Alerts':>6} Status"
    )
    click.echo("-" * 90)

    for company in COMPANIES:
        state = states.get(company.name)
        status_label = (
            _company_status(company, state, settings)
            if company.enabled
            else "off"
        )
        enabled = "yes" if company.enabled else "no"
        click.echo(
            f"{company.name:<20} {enabled:>3} "
            f"{_format_timestamp(state.last_checked if state else None):<22} "
            f"{_format_timestamp(state.last_alerted if state else None):<22} "
            f"{state.alert_count if state else 0:>6} {status_label}"
        )

    stats = store.get_stats()
    click.echo()
    click.echo(
        f"Monitored: {stats['companies_monitored']} | "
        f"Total alerts: {stats['total_alerts']} | "
        f"Poll interval: {poll_interval // 60} min | "
        f"Uptime: {stats['uptime_hours']} h"
    )


@cli.command()
@click.option("--limit", default=20, show_default=True, help="Max recent alerts to show.")
def alerts(limit: int) -> None:
    """List recent alerts and per-channel delivery results."""
    setup_logging()
    store = StateStore()
    rows = store.get_recent_alerts(limit=limit)

    if not rows:
        click.echo("No alerts logged yet.")
        return

    click.echo(f"Recent alerts (limit={limit})")
    click.echo(
        f"{'Detected':<22} {'Company':<15} {'Keyword':<10} "
        f"{'SMS':>4} {'Call':>4} {'Push':>4} {'Email':>5}"
    )
    click.echo("-" * 75)

    for row in rows:
        click.echo(
            f"{_format_timestamp(row.get('detected_at')):<22} "
            f"{str(row.get('company', '')):<15} "
            f"{str(row.get('trigger_keyword', '')):<10} "
            f"{'ok' if row.get('sms_ok', 0) else 'x':>4} "
            f"{'ok' if row.get('call_ok', 0) else 'x':>4} "
            f"{'ok' if row.get('push_ok', 0) else 'x':>4} "
            f"{'ok' if row.get('email_ok', 0) else 'x':>5}"
        )


@cli.command("test-alerts")
def test_alerts() -> None:
    """Send a test alert through all notification channels."""
    setup_logging()
    settings = get_settings()
    profile = load_profile()
    alert_manager = AlertManager(settings, profile)
    payload = AlertPayload(
        company="Test Company",
        url="https://example.com/careers/test",
        job_title="Software Engineering Intern",
        job_url="https://example.com/careers/test/jobs/123",
        relevance_score=9,
        tier="high",
        trigger_keyword="intern",
        detected_at=datetime.now(timezone.utc).isoformat(),
        diff_snippet=(
            "CLI test alert — no action required. "
            "This confirms all notification channels are wired correctly."
        ),
    )

    click.echo("Sending high-tier test alert to all channels...")
    results = alert_manager.fire(payload)

    for channel in CHANNELS:
        ok = results.get(channel, False)
        click.echo(f"  {'ok' if ok else 'FAIL'} {channel.upper()}")

    succeeded = sum(1 for ok in results.values() if ok)
    click.echo(f"\n{succeeded}/{len(CHANNELS)} channels succeeded.")
    if succeeded < len(CHANNELS):
        click.echo("Some channels failed — verify credentials in .env and run again.")


@cli.command()
@click.argument("company_name")
def toggle(company_name: str) -> None:
    """Enable or disable monitoring for a company in companies.py."""
    enabled = _toggle_company_enabled(company_name)
    state = "enabled" if enabled else "disabled"
    click.echo(
        f'"{company_name}" is now {state}. '
        "Restart the monitor for changes to take effect."
    )


@cli.command()
def run() -> None:
    """Start the internship monitor daemon."""
    run_monitor()


if __name__ == "__main__":
    cli()
