from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AlertTier = Literal["standard", "high"]


@dataclass(frozen=True, slots=True)
class JobPosting:
    id: str
    title: str
    department: str
    location: str
    url: str
    description: str
    company_name: str
    # ISO 8601 publish time, when the source reports one. Empty means unknown,
    # which callers must treat as "do not filter on age".
    posted_at: str = ""


@dataclass(frozen=True, slots=True)
class CompanyConfig:
    name: str
    url: str
    level_keywords: list[str]
    cycle_keywords: list[str]
    enabled: bool

    def all_keywords(self) -> tuple[str, ...]:
        """All configured level and cycle terms (for diff/snippet search)."""
        return (*self.level_keywords, *self.cycle_keywords)


@dataclass(frozen=True, slots=True)
class AlertPayload:
    company: str
    url: str
    trigger_keyword: str
    detected_at: str
    diff_snippet: str
    job_title: str = ""
    job_url: str = ""
    job_id: str = ""
    relevance_score: int = 0
    tier: AlertTier = "standard"
    notification_keywords: tuple[str, ...] = ()
    dedup_key: str = ""
    pending_hash: str = ""
    pending_text: str = ""


@dataclass(frozen=True, slots=True)
class ClosedJobEvent:
    company: str
    job_id: str
    job_title: str
    detected_at: str
    company_url: str = ""


@dataclass(frozen=True, slots=True)
class PollResult:
    alerts: tuple[AlertPayload, ...] = ()
    closed_jobs: tuple[ClosedJobEvent, ...] = ()


@dataclass(slots=True)
class StateRecord:
    company: str
    url: str
    last_hash: str
    last_checked: str
    last_alerted: str | None
    alert_count: int
    last_text: str = ""
    seen_job_ids: str = "[]"
    seen_job_titles: str = "{}"
