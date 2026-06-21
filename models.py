from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompanyConfig:
    name: str
    url: str
    keywords: list[str]
    enabled: bool


@dataclass(frozen=True, slots=True)
class AlertPayload:
    company: str
    url: str
    trigger_keyword: str
    detected_at: str
    diff_snippet: str


@dataclass(slots=True)
class StateRecord:
    company: str
    url: str
    last_hash: str
    last_checked: str
    last_alerted: str | None
    alert_count: int
