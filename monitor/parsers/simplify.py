"""Parser for the SimplifyJobs internship aggregator feed.

Source: https://github.com/SimplifyJobs/Summer<YEAR>-Internships

The repo publishes a structured ``listings.json`` with one entry per internship
across hundreds of companies. We treat the whole feed as a single job-board
source: the scraper diffs stable listing IDs and emits one alert per genuinely
new posting, scored and filtered like any other board.

Each company's real name is folded into the job title so notifications stay
informative (the alert's company field is the aggregator, "Simplify").
"""

from __future__ import annotations

import json
from typing import Any

from monitor.models import JobPosting

# Stable host fragment for raw listing files, used for URL detection.
_SIMPLIFY_HOST = "raw.githubusercontent.com/simplifyjobs"


def simplify_listings_url(year: int) -> str:
    """Raw ``listings.json`` URL for the Summer<year> internship repo."""
    return (
        "https://raw.githubusercontent.com/SimplifyJobs/"
        f"Summer{year}-Internships/dev/.github/scripts/listings.json"
    )


def is_simplify_url(url: str) -> bool:
    lowered = url.lower()
    return _SIMPLIFY_HOST in lowered and "listings.json" in lowered


def _join(value: Any) -> str:
    """Flatten a list-or-scalar field to a comma-separated string."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value or "")


def parse_simplify(
    raw_json: str | list[Any], company_name: str = ""
) -> list[JobPosting]:
    """Map active, visible Simplify listings to :class:`JobPosting` records."""
    data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    if not isinstance(data, list):
        return []

    jobs: list[JobPosting] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if not (entry.get("active") and entry.get("is_visible")):
            continue

        url = str(entry.get("url") or "").strip()
        if not url:
            continue  # no apply link -> useless to alert on; skip

        company = str(entry.get("company_name") or "").strip() or "Unknown"
        role = str(entry.get("title") or "").strip()
        # Fold the employer into the title so the push/email name the company.
        title = f"{company} — {role}" if role else company

        category = str(entry.get("category") or "").strip()
        # Description carries the cycle term ("Summer 2027") and degrees so the
        # level+cycle keyword match fires exactly like other boards.
        description = " ".join(
            part
            for part in (_join(entry.get("terms")), category, _join(entry.get("degrees")))
            if part
        )

        jobs.append(
            JobPosting(
                id=str(entry.get("id") or "").strip() or url,
                title=title,
                department=category,
                location=_join(entry.get("locations")),
                url=url,
                description=description,
                company_name=company,
            )
        )
    return jobs
