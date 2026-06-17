"""Shared data models for the internship monitor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompanyConfig:
    """Configuration for a single company careers page to monitor."""

    name: str
    url: str
    keywords: list[str]
    enabled: bool


@dataclass(frozen=True, slots=True)
class AlertPayload:
    """Payload emitted when a keyword match is detected on a careers page."""

    company: str
    url: str
    trigger_keyword: str
    detected_at: str  # ISO 8601
    diff_snippet: str


@dataclass(slots=True)
class StateRecord:
    """Persistent state for a monitored company between poll cycles."""

    company: str
    url: str
    last_hash: str
    last_checked: str
    last_alerted: str | None
    alert_count: int
    last_text: str = ""
