"""Command-line interface for the internship monitor."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from rich.console import Console
from rich.table import Table

from alerts import AlertManager
from companies import COMPANIES
from config import Settings, get_settings, setup_logging
from main import get_poll_interval, main as run_monitor
from models import AlertPayload, CompanyConfig, StateRecord
from storage import StateStore

console = Console()
COMPANIES_PATH = Path(__file__).resolve().parent / "companies.py"
PACIFIC = ZoneInfo("America/Los_Angeles")

STATUS_OK = "OK"
STATUS_CHANGED = "CHANGED"
STATUS_ERROR = "ERROR"

CHANNELS: tuple[str, ...] = ("sms", "call", "push", "email")


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp into an aware UTC datetime."""
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
    """Format a stored ISO timestamp for display in Pacific time."""
    parsed = _parse_iso(value)
    if parsed is None:
        return "—"
    return parsed.astimezone(PACIFIC).strftime("%Y-%m-%d %H:%M %Z")


def _company_status(
    company: CompanyConfig,
    state: StateRecord | None,
    settings: Settings,
) -> str:
    """Derive OK / CHANGED / ERROR status for a monitored company.

    - ``ERROR``: never checked, invalid timestamps, or last check is stale.
    - ``CHANGED``: non-empty content hash and a recent alert was recorded.
    - ``OK``: checked recently with no recent alert activity.
    """
    if state is None or not state.last_checked.strip():
        return STATUS_ERROR

    last_checked = _parse_iso(state.last_checked)
    if last_checked is None:
        return STATUS_ERROR

    now = datetime.now(timezone.utc)
    poll_interval = get_poll_interval(settings)
    stale_threshold = poll_interval * 2

    if (now - last_checked).total_seconds() > stale_threshold:
        return STATUS_ERROR

    if state.last_hash.strip() and state.last_alerted:
        last_alerted = _parse_iso(state.last_alerted)
        if last_alerted is not None:
            alert_age = (now - last_alerted).total_seconds()
            if alert_age <= settings.min_alert_interval:
                return STATUS_CHANGED

    return STATUS_OK


def _status_style(status: str) -> str:
    """Return rich markup for a status label."""
    styles = {
        STATUS_OK: "[bold green]OK[/bold green]",
        STATUS_CHANGED: "[bold yellow]CHANGED[/bold yellow]",
        STATUS_ERROR: "[bold red]ERROR[/bold red]",
    }
    return styles.get(status, status)


def _channel_indicator(ok: bool | int) -> str:
    """Render a channel delivery result as a colored symbol."""
    return "[bold green]✓[/bold green]" if bool(ok) else "[bold red]✗[/bold red]"


def _toggle_company_enabled(company_name: str) -> bool:
    """Flip the ``enabled`` flag for *company_name* in ``companies.py``.

    Returns:
        The new enabled value after toggling.
    """
    content = COMPANIES_PATH.read_text(encoding="utf-8")
    pattern = (
        rf'(CompanyConfig\(\s*name="{re.escape(company_name)}"[\s\S]*?enabled=)'
        r"(True|False)"
    )
    match = re.search(pattern, content)
    if match is None:
        raise click.ClickException(
            f'Company "{company_name}" not found in companies.py. '
            "Use an exact name from the status table."
        )

    current = match.group(2) == "True"
    new_value = "False" if current else "True"
    updated = content[: match.start(2)] + new_value + content[match.end(2) :]
    COMPANIES_PATH.write_text(updated, encoding="utf-8")
    return new_value == "True"


def _make_test_payload() -> AlertPayload:
    """Build a synthetic alert payload for channel smoke tests."""
    return AlertPayload(
        company="Test Company",
        url="https://example.com/careers/test",
        trigger_keyword="intern",
        detected_at=datetime.now(timezone.utc).isoformat(),
        diff_snippet=(
            "CLI test alert — no action required. "
            "This confirms all notification channels are wired correctly."
        ),
    )


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

    table = Table(title="Internship Monitor Status", show_lines=True)
    table.add_column("Company", style="cyan", no_wrap=True)
    table.add_column("Enabled", justify="center")
    table.add_column("Last Checked")
    table.add_column("Last Alerted")
    table.add_column("Alerts", justify="right")
    table.add_column("Status", justify="center")

    for company in COMPANIES:
        state = states.get(company.name)
        if company.enabled:
            status_label = _company_status(company, state, settings)
            status_cell = _status_style(status_label)
        else:
            status_cell = "[dim]off[/dim]"

        enabled_label = (
            "[green]yes[/green]" if company.enabled else "[dim]no[/dim]"
        )
        table.add_row(
            company.name,
            enabled_label,
            _format_timestamp(state.last_checked if state else None),
            _format_timestamp(state.last_alerted if state else None),
            str(state.alert_count if state else 0),
            status_cell,
        )

    stats = store.get_stats()
    console.print(table)
    console.print(
        f"\n[dim]Monitored in DB: {stats['companies_monitored']} | "
        f"Total alerts: {stats['total_alerts']} | "
        f"Poll interval: {poll_interval // 60} min | "
        f"Uptime: {stats['uptime_hours']} h[/dim]"
    )


@cli.command()
@click.option(
    "--limit",
    default=20,
    show_default=True,
    help="Maximum number of recent alerts to display.",
)
def alerts(limit: int) -> None:
    """List recent alerts and per-channel delivery results."""
    setup_logging()
    store = StateStore()
    rows = store.get_recent_alerts(limit=limit)

    table = Table(title=f"Recent Alerts (limit={limit})", show_lines=True)
    table.add_column("Detected", no_wrap=True)
    table.add_column("Company", style="cyan")
    table.add_column("Keyword")
    table.add_column("SMS", justify="center")
    table.add_column("Call", justify="center")
    table.add_column("Push", justify="center")
    table.add_column("Email", justify="center")

    if not rows:
        console.print("[yellow]No alerts logged yet.[/yellow]")
        return

    for row in rows:
        table.add_row(
            _format_timestamp(row.get("detected_at")),
            str(row.get("company", "")),
            str(row.get("trigger_keyword", "")),
            _channel_indicator(row.get("sms_ok", 0)),
            _channel_indicator(row.get("call_ok", 0)),
            _channel_indicator(row.get("push_ok", 0)),
            _channel_indicator(row.get("email_ok", 0)),
        )

    console.print(table)


@cli.command("test-alerts")
def test_alerts() -> None:
    """Send a test alert through all notification channels."""
    setup_logging()
    settings = get_settings()
    alert_manager = AlertManager(settings)
    payload = _make_test_payload()

    console.print("[bold]Sending test alert to all channels…[/bold]\n")
    results = alert_manager.fire_all(payload)

    for channel in CHANNELS:
        ok = results.get(channel, False)
        symbol = "[bold green]✓[/bold green]" if ok else "[bold red]✗[/bold red]"
        console.print(f"  {symbol} {channel.upper()}")

    succeeded = sum(1 for ok in results.values() if ok)
    console.print(
        f"\n[dim]{succeeded}/{len(CHANNELS)} channels succeeded.[/dim]"
    )
    if succeeded < len(CHANNELS):
        console.print(
            "[yellow]Some channels failed — verify credentials in .env "
            "and run again.[/yellow]"
        )


@cli.command()
@click.argument("company_name")
def toggle(company_name: str) -> None:
    """Enable or disable monitoring for a company in companies.py."""
    enabled = _toggle_company_enabled(company_name)
    state = "enabled" if enabled else "disabled"
    console.print(
        f'[green]✓[/green] "{company_name}" is now [bold]{state}[/bold]. '
        "Restart the monitor for changes to take effect."
    )


@cli.command()
def run() -> None:
    """Start the internship monitor daemon."""
    run_monitor()


if __name__ == "__main__":
    cli()
