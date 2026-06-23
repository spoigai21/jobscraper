"""Apple Jobs search hydration parser."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from monitor.config import PAGE_FETCH_DELAY_SECONDS
from monitor.models import JobPosting

logger = logging.getLogger(__name__)

APPLE_JOBS_BASE = "https://jobs.apple.com"
APPLE_PAGE_SIZE = 20
MAX_PAGINATION_PAGES = 50

_HYDRATION_RE = re.compile(
    r'window\.__staticRouterHydrationData = JSON\.parse\("(.+?)"\);',
    re.DOTALL,
)


def is_apple_jobs_url(url: str) -> bool:
    """Return True when *url* targets Apple Jobs search."""
    lowered = url.lower()
    return "jobs.apple.com" in lowered and "/search" in lowered


def apple_page_url(url: str, *, page: int) -> str:
    """Return *url* with ``page`` query parameter set."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page)]
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(query, doseq=True), "")
    )


def _apple_headers(user_agent: str, referer: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }


def parse_apple_hydration(html: str) -> dict[str, Any] | None:
    """Extract ``loaderData.search`` from SSR hydration HTML."""
    match = _HYDRATION_RE.search(html)
    if not match:
        return None

    try:
        decoded = match.group(1).encode().decode("unicode_escape")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Apple Jobs hydration JSON decode failed: %s", exc)
        return None

    loader_data = payload.get("loaderData")
    if not isinstance(loader_data, dict):
        return None

    search = loader_data.get("search")
    if not isinstance(search, dict):
        return None

    return search


def _apple_location(job: dict[str, Any]) -> str:
    locations = job.get("locations") or []
    if not isinstance(locations, list):
        return ""
    names: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        name = str(location.get("name") or "").strip()
        if name:
            names.append(name)
    return ", ".join(names)


def _apple_department(job: dict[str, Any]) -> str:
    team = job.get("team")
    if isinstance(team, dict):
        return str(team.get("teamName") or "").strip()
    return ""


def _apple_job_id(job: dict[str, Any]) -> str:
    return str(job.get("reqId") or job.get("id") or job.get("positionId") or "").strip()


def _apple_details_url(job: dict[str, Any]) -> str:
    posting_id = _apple_job_id(job)
    slug = str(job.get("transformedPostingTitle") or "").strip()
    if not posting_id:
        return ""
    if slug:
        return f"{APPLE_JOBS_BASE}/en-us/details/{posting_id}/{slug}"
    return f"{APPLE_JOBS_BASE}/en-us/details/{posting_id}"


def fetch_apple_search_raw(
    url: str,
    *,
    user_agent: str,
    timeout: int,
) -> str | None:
    """Fetch Apple job-search results via paginated SSR hydration HTML."""
    referer = url.split("?", 1)[0] if "?" in url else url
    session = requests.Session()
    all_results: list[dict[str, Any]] = []
    seen_job_ids: set[str] = set()
    total_records: int | None = None

    for page in range(1, MAX_PAGINATION_PAGES + 1):
        page_url = apple_page_url(url, page=page)
        try:
            response = session.get(
                page_url,
                headers=_apple_headers(user_agent, referer),
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.warning("Apple Jobs search fetch failed on page %d: %s", page, exc)
            break

        search = parse_apple_hydration(response.text)
        if not search:
            logger.warning("Apple Jobs hydration data missing on page %d", page)
            break

        if total_records is None:
            try:
                total_records = int(search.get("totalRecords") or 0)
            except (TypeError, ValueError):
                total_records = 0

        page_results = search.get("searchResults") or []
        if not isinstance(page_results, list) or not page_results:
            break

        for item in page_results:
            if not isinstance(item, dict):
                continue
            job_id = _apple_job_id(item)
            if job_id and job_id not in seen_job_ids:
                seen_job_ids.add(job_id)
                all_results.append(item)

        if total_records is not None and len(all_results) >= total_records:
            break
        if page >= MAX_PAGINATION_PAGES:
            break

        time.sleep(PAGE_FETCH_DELAY_SECONDS)

    if not all_results:
        return None

    return json.dumps(
        {
            "searchResults": all_results,
            "totalRecords": total_records if total_records is not None else len(all_results),
        }
    )


def parse_apple(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    """Parse Apple Jobs hydration ``searchResults`` payload."""
    if isinstance(raw_json, dict):
        payload = raw_json
    else:
        payload = json.loads(raw_json)

    results = payload.get("searchResults") or []
    if not isinstance(results, list):
        return []

    postings: list[JobPosting] = []
    for job in results:
        if not isinstance(job, dict):
            continue
        job_id = _apple_job_id(job)
        title = str(job.get("postingTitle") or "").strip()
        if not job_id or not title:
            continue

        postings.append(
            JobPosting(
                id=job_id,
                title=title,
                department=_apple_department(job),
                location=_apple_location(job),
                url=_apple_details_url(job),
                description=str(job.get("jobSummary") or ""),
                company_name=company_name,
            )
        )

    return postings
