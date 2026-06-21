"""Per-job parsing for Greenhouse, Ashby, and Lever job board APIs."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

from models import JobPosting

__all__ = [
    "BoardType",
    "JobPosting",
    "detect_board_type",
    "format_new_jobs_snippet",
    "job_matches_keyword",
    "jobs_to_text",
    "parse_ashby",
    "parse_greenhouse",
    "parse_job_board",
    "parse_lever",
]


class BoardType(str, Enum):
    GREENHOUSE = "greenhouse"
    ASHBY = "ashby"
    LEVER = "lever"
    WORKDAY = "workday"
    HTML = "html"
    UNKNOWN = "unknown"


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _load_json(raw_json: str | dict[str, Any] | list[Any]) -> dict[str, Any] | list[Any]:
    if isinstance(raw_json, (dict, list)):
        return raw_json
    return json.loads(raw_json)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", text)).strip()


def _first_department_name(departments: Any) -> str:
    if not isinstance(departments, list):
        return ""
    for dept in departments:
        if isinstance(dept, dict):
            name = dept.get("name")
            if name:
                return str(name)
    return ""


def _greenhouse_location(job: dict[str, Any]) -> str:
    location = job.get("location")
    if isinstance(location, dict):
        return str(location.get("name") or "")
    if location:
        return str(location)
    offices = job.get("offices") or []
    if isinstance(offices, list) and offices:
        first = offices[0]
        if isinstance(first, dict):
            return str(first.get("name") or "")
    return ""


def detect_board_type(url: str) -> BoardType:
    lowered = url.lower()
    if "boards-api.greenhouse.io" in lowered:
        return BoardType.GREENHOUSE
    if "api.ashbyhq.com/posting-api" in lowered:
        return BoardType.ASHBY
    if "api.lever.co/v0/postings" in lowered:
        return BoardType.LEVER
    if "/wday/cxs/" in lowered:
        return BoardType.WORKDAY
    if url.startswith(("http://", "https://")):
        return BoardType.HTML
    return BoardType.UNKNOWN


def parse_greenhouse(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    data = _load_json(raw_json)
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    postings: list[JobPosting] = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        if job_id is None:
            continue
        postings.append(
            JobPosting(
                id=str(job_id),
                title=str(job.get("title") or ""),
                department=_first_department_name(job.get("departments")),
                location=_greenhouse_location(job),
                url=str(job.get("absolute_url") or ""),
                description=_strip_html(str(job.get("content") or "")),
                company_name=company_name,
            )
        )

    return postings


def parse_ashby(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    data = _load_json(raw_json)
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    postings: list[JobPosting] = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        if job_id is None:
            continue
        department = str(job.get("department") or job.get("team") or "")
        description = str(
            job.get("descriptionPlain")
            or _strip_html(str(job.get("descriptionHtml") or ""))
            or ""
        )
        postings.append(
            JobPosting(
                id=str(job_id),
                title=str(job.get("title") or ""),
                department=department,
                location=str(job.get("location") or ""),
                url=str(job.get("jobUrl") or ""),
                description=description,
                company_name=company_name,
            )
        )

    return postings


def parse_lever(raw_json: str | list[Any], company_name: str) -> list[JobPosting]:
    data = _load_json(raw_json)
    jobs = data if isinstance(data, list) else []
    postings: list[JobPosting] = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        if job_id is None:
            continue
        categories = job.get("categories") or {}
        if not isinstance(categories, dict):
            categories = {}
        department = str(
            categories.get("team")
            or categories.get("department")
            or categories.get("commitment")
            or ""
        )
        location = str(categories.get("location") or "")
        description = str(
            job.get("descriptionPlain")
            or _strip_html(str(job.get("description") or ""))
            or ""
        )
        postings.append(
            JobPosting(
                id=str(job_id),
                title=str(job.get("text") or ""),
                department=department,
                location=location,
                url=str(job.get("hostedUrl") or job.get("applyUrl") or ""),
                description=description,
                company_name=company_name,
            )
        )

    return postings


def parse_job_board(
    raw_json: str | dict[str, Any] | list[Any],
    url: str,
    company_name: str,
) -> list[JobPosting]:
    board_type = detect_board_type(url)
    if board_type == BoardType.GREENHOUSE:
        return parse_greenhouse(raw_json, company_name)
    if board_type == BoardType.ASHBY:
        return parse_ashby(raw_json, company_name)
    if board_type == BoardType.LEVER:
        return parse_lever(raw_json, company_name)
    return []


def jobs_to_text(jobs: list[JobPosting]) -> str:
    parts: list[str] = []
    for job in jobs:
        parts.extend(
            [job.title, job.department, job.location, job.description, job.company_name]
        )
    return " ".join(part for part in parts if part).lower()


def job_matches_keyword(job: JobPosting, keywords: list[str]) -> str | None:
    searchable = " ".join(
        [job.title, job.department, job.location, job.description]
    ).lower()
    for keyword in keywords:
        lowered_keyword = keyword.lower()
        if lowered_keyword in {"intern", "2027"}:
            if re.search(rf"\b{re.escape(lowered_keyword)}\b", searchable):
                return keyword
        elif lowered_keyword in searchable:
            return keyword
    return None


def format_new_jobs_snippet(jobs: list[JobPosting], *, limit: int = 3) -> str:
    if not jobs:
        return "New job listings detected"
    lines: list[str] = []
    for job in jobs[:limit]:
        detail = job.title
        meta = ", ".join(part for part in (job.department, job.location) if part)
        if meta:
            detail = f"{detail} ({meta})"
        lines.append(detail)
    snippet = "; ".join(lines)
    if len(jobs) > limit:
        snippet = f"{snippet}; +{len(jobs) - limit} more"
    return f"New: {snippet[:280]}"
