"""Per-job parsing for Greenhouse, Ashby, and Lever job board APIs."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from monitor.models import JobPosting
from monitor.parsers.amazon import is_amazon_jobs_url, parse_amazon
from monitor.parsers.apple import is_apple_jobs_url, parse_apple
from monitor.parsers.bytedance import is_bytedance_jobs_url, parse_bytedance
from monitor.parsers.google import is_google_careers_url, parse_google, parse_google_html
from monitor.parsers.hubspot import is_hubspot_jobs_url, parse_hubspot
from monitor.parsers.meta import is_meta_jobs_url, parse_meta
from monitor.parsers.simplify import is_simplify_url, parse_simplify
from monitor.parsers.tiktok import is_tiktok_jobs_url, parse_tiktok

__all__ = [
    "BoardType",
    "JobPosting",
    "detect_board_type",
    "format_new_jobs_snippet",
    "job_matches_keyword",
    "job_matches_level_and_cycle",
    "match_level_and_cycle_in_text",
    "jobs_to_text",
    "parse_amazon",
    "parse_apple",
    "parse_ashby",
    "parse_bytedance",
    "parse_google",
    "parse_google_html",
    "parse_greenhouse",
    "parse_hubspot",
    "parse_job_board",
    "parse_lever",
    "parse_meta",
    "parse_microsoft",
    "parse_simplify",
    "parse_tiktok",
    "parse_uber",
    "parse_workday",
]


class BoardType(str, Enum):
    GREENHOUSE = "greenhouse"
    ASHBY = "ashby"
    LEVER = "lever"
    WORKDAY = "workday"
    UBER = "uber"
    MICROSOFT = "microsoft"
    META = "meta"
    AMAZON = "amazon"
    APPLE = "apple"
    GOOGLE = "google"
    BYTEDANCE = "bytedance"
    TIKTOK = "tiktok"
    HUBSPOT = "hubspot"
    SIMPLIFY = "simplify"
    HTML = "html"
    UNKNOWN = "unknown"


MICROSOFT_CAREERS_BASE = "https://apply.careers.microsoft.com"


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


def _uber_location(job: dict[str, Any]) -> str:
    location = job.get("location")
    if isinstance(location, dict):
        city = str(location.get("city") or "").strip()
        country = str(
            location.get("countryName") or location.get("country") or ""
        ).strip()
        parts = [part for part in (city, country) if part]
        if parts:
            return ", ".join(parts)
    if location:
        return str(location)
    return ""


def detect_board_type(url: str) -> BoardType:
    lowered = url.lower()
    if "boards-api.greenhouse.io" in lowered:
        return BoardType.GREENHOUSE
    if "api.ashbyhq.com/posting-api" in lowered:
        return BoardType.ASHBY
    if "lever.co/v0/postings" in lowered:
        return BoardType.LEVER
    if "/wday/cxs/" in lowered:
        return BoardType.WORKDAY
    if "uber.com/api/loadsearchjobsresults" in lowered:
        return BoardType.UBER
    if "/api/pcsx/search" in lowered or "/api/apply/v2/jobs" in lowered:
        return BoardType.MICROSOFT
    if is_meta_jobs_url(url):
        return BoardType.META
    if is_amazon_jobs_url(url):
        return BoardType.AMAZON
    if is_apple_jobs_url(url):
        return BoardType.APPLE
    if is_google_careers_url(url):
        return BoardType.GOOGLE
    if is_bytedance_jobs_url(url):
        return BoardType.BYTEDANCE
    if is_tiktok_jobs_url(url):
        return BoardType.TIKTOK
    if is_hubspot_jobs_url(url):
        return BoardType.HUBSPOT
    if is_simplify_url(url):
        return BoardType.SIMPLIFY
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


def parse_uber(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    data = _load_json(raw_json)
    results: list[Any] = []
    if isinstance(data, dict):
        nested = data.get("data", {})
        if isinstance(nested, dict):
            results = nested.get("results") or []
    if not isinstance(results, list):
        results = []

    postings: list[JobPosting] = []
    for job in results:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        if job_id is None:
            continue
        department = str(job.get("team") or job.get("department") or "")
        postings.append(
            JobPosting(
                id=str(job_id),
                title=str(job.get("title") or ""),
                department=department,
                location=_uber_location(job),
                url=f"https://www.uber.com/us/en/careers/list/{job_id}",
                description=str(job.get("description") or ""),
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


def _workday_public_base_url(board_url: str) -> str:
    """Derive the public careers site base URL from a Workday cxs API URL."""
    parsed = urlparse(board_url.split("?", 1)[0])
    parts = [part for part in parsed.path.split("/") if part]
    try:
        cxs_idx = parts.index("cxs")
        site = parts[cxs_idx + 2]
    except (ValueError, IndexError):
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/en-US/{site}"


def _workday_job_id(job: dict[str, Any]) -> str | None:
    """Return a stable Workday job ID.

    Prefer ``bulletFields[0]`` (requisition id, e.g. ``JR123``). When that is
    missing, fall back to the ``externalPath`` basename so slug-only paths do
    not churn IDs when the listing URL prefix changes.
    """
    bullet_fields = job.get("bulletFields")
    if isinstance(bullet_fields, list) and bullet_fields:
        bullet_id = str(bullet_fields[0]).strip()
        if bullet_id:
            return bullet_id
    external_path = str(job.get("externalPath") or "").strip()
    if external_path:
        basename = external_path.rstrip("/").rsplit("/", 1)[-1]
        if basename:
            return basename
    return None


def _workday_job_url(job: dict[str, Any], board_url: str) -> str:
    external_path = str(job.get("externalPath") or "")
    if not external_path:
        return ""
    base = _workday_public_base_url(board_url)
    if not base:
        return external_path
    return f"{base}{external_path}"


def _microsoft_location(job: dict[str, Any]) -> str:
    locations = job.get("locations")
    if isinstance(locations, list) and locations:
        return str(locations[0])
    standardized = job.get("standardizedLocations")
    if isinstance(standardized, list) and standardized:
        return str(standardized[0])
    location = job.get("location")
    if location:
        return str(location)
    return ""


def _microsoft_job_url(job: dict[str, Any], board_url: str = "") -> str:
    canonical_url = job.get("canonicalPositionUrl")
    if canonical_url:
        return str(canonical_url)
    public_url = job.get("publicUrl")
    if public_url:
        return str(public_url)
    position_url = str(job.get("positionUrl") or "")
    if position_url:
        if position_url.startswith(("http://", "https://")):
            return position_url
        parsed = urlparse(board_url)
        base = (
            f"{parsed.scheme}://{parsed.netloc}"
            if board_url
            else MICROSOFT_CAREERS_BASE
        )
        return f"{base}{position_url}"
    job_id = job.get("id")
    if job_id is not None:
        return f"{MICROSOFT_CAREERS_BASE}/careers/job/{job_id}"
    return ""


def _microsoft_positions(raw_json: str | dict[str, Any]) -> list[Any]:
    data = _load_json(raw_json)
    if not isinstance(data, dict):
        return []
    positions = data.get("positions")
    if isinstance(positions, list):
        return positions
    nested = data.get("data")
    if isinstance(nested, dict):
        positions = nested.get("positions")
        if isinstance(positions, list):
            return positions
    return []


def parse_microsoft(
    raw_json: str | dict[str, Any],
    company_name: str,
    board_url: str = "",
) -> list[JobPosting]:
    postings: list[JobPosting] = []

    for job in _microsoft_positions(raw_json):
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        if job_id is None:
            continue
        description = _strip_html(
            str(job.get("jobDescription") or job.get("job_description") or "")
        )
        postings.append(
            JobPosting(
                id=str(job_id),
                title=str(job.get("name") or ""),
                department=str(job.get("department") or ""),
                location=_microsoft_location(job),
                url=_microsoft_job_url(job, board_url),
                description=description,
                company_name=company_name,
            )
        )

    return postings


def parse_workday(
    raw_json: str | dict[str, Any],
    company_name: str,
    board_url: str = "",
) -> list[JobPosting]:
    data = _load_json(raw_json)
    jobs = data.get("jobPostings", []) if isinstance(data, dict) else []
    postings: list[JobPosting] = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = _workday_job_id(job)
        if job_id is None:
            continue
        postings.append(
            JobPosting(
                id=job_id,
                title=str(job.get("title") or ""),
                department="",
                location=str(job.get("locationsText") or ""),
                url=_workday_job_url(job, board_url),
                description="",
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
    if board_type == BoardType.UBER:
        return parse_uber(raw_json, company_name)
    if board_type == BoardType.WORKDAY:
        return parse_workday(raw_json, company_name, board_url=url)
    if board_type == BoardType.MICROSOFT:
        return parse_microsoft(raw_json, company_name, board_url=url)
    if board_type == BoardType.META:
        return parse_meta(raw_json, company_name)
    if board_type == BoardType.AMAZON:
        return parse_amazon(raw_json, company_name)
    if board_type == BoardType.APPLE:
        return parse_apple(raw_json, company_name)
    if board_type == BoardType.GOOGLE:
        return parse_google(raw_json, company_name)
    if board_type == BoardType.BYTEDANCE:
        return parse_bytedance(raw_json, company_name)
    if board_type == BoardType.TIKTOK:
        return parse_tiktok(raw_json, company_name)
    if board_type == BoardType.HUBSPOT:
        return parse_hubspot(raw_json, company_name)
    if board_type == BoardType.SIMPLIFY:
        return parse_simplify(raw_json, company_name)
    return []


def jobs_to_text(jobs: list[JobPosting]) -> str:
    parts: list[str] = []
    for job in jobs:
        parts.extend(
            [job.title, job.department, job.location, job.description, job.company_name]
        )
    return " ".join(part for part in parts if part).lower()


def _text_matches_keyword(text: str, keyword: str) -> bool:
    lowered_keyword = keyword.lower()
    if lowered_keyword in {"intern", "2027"}:
        return bool(re.search(rf"\b{re.escape(lowered_keyword)}\b", text))
    return lowered_keyword in text


def _first_matching_keyword(text: str, keywords: list[str]) -> str | None:
    for keyword in keywords:
        if _text_matches_keyword(text, keyword):
            return keyword
    return None


def match_level_and_cycle_in_text(
    text: str,
    level_keywords: list[str],
    cycle_keywords: list[str],
) -> str | None:
    """Return the matched cycle keyword when both groups match, else None."""
    lowered = text.lower()
    if _first_matching_keyword(lowered, level_keywords) is None:
        return None
    return _first_matching_keyword(lowered, cycle_keywords)


def job_matches_level_and_cycle(
    job: JobPosting,
    level_keywords: list[str],
    cycle_keywords: list[str],
) -> str | None:
    """Require a level term and a cycle term; return the cycle match as trigger."""
    searchable = " ".join(
        [job.title, job.department, job.location, job.description]
    ).lower()
    return match_level_and_cycle_in_text(
        searchable, level_keywords, cycle_keywords
    )


def job_matches_keyword(job: JobPosting, keywords: list[str]) -> str | None:
    """Return the first OR-matched keyword from a flat list (legacy helper)."""
    searchable = " ".join(
        [job.title, job.department, job.location, job.description]
    ).lower()
    return _first_matching_keyword(searchable, keywords)


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
