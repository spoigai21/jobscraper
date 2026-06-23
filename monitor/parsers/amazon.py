"""Amazon Jobs search.json parser."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from monitor.config import PAGE_FETCH_DELAY_SECONDS
from monitor.models import JobPosting

logger = logging.getLogger(__name__)

AMAZON_JOBS_BASE = "https://www.amazon.jobs"
MAX_RESULT_LIMIT = 100
MAX_PAGINATION_PAGES = 50


def is_amazon_jobs_url(url: str) -> bool:
    """Return True when *url* targets Amazon Jobs search."""
    lowered = url.lower()
    return "amazon.jobs" in lowered and "/search" in lowered


def amazon_search_json_url(
    url: str,
    *,
    offset: int = 0,
    result_limit: int = MAX_RESULT_LIMIT,
) -> str:
    """Convert a human-readable Amazon Jobs search URL to ``search.json``."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith("/search.json"):
        json_path = path
    elif path.endswith("/search"):
        json_path = f"{path}.json"
    else:
        json_path = path.replace("/search", "/search.json", 1)

    query = parse_qs(parsed.query, keep_blank_values=True)
    query["offset"] = [str(offset)]
    query["result_limit"] = [str(min(result_limit, MAX_RESULT_LIMIT))]

    return urlunparse(
        (parsed.scheme, parsed.netloc, json_path, "", urlencode(query, doseq=True), "")
    )


def _amazon_headers(user_agent: str, referer: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def _amazon_location(job: dict[str, Any]) -> str:
    normalized = str(job.get("normalized_location") or "").strip()
    if normalized:
        return normalized
    location = str(job.get("location") or "").strip()
    if location:
        return location
    city = str(job.get("city") or "").strip()
    state = str(job.get("state") or "").strip()
    parts = [part for part in (city, state) if part]
    return ", ".join(parts)


def _amazon_department(job: dict[str, Any]) -> str:
    category = str(job.get("job_category") or "").strip()
    family = str(job.get("job_family") or "").strip()
    if category and family:
        return f"{category} / {family}"
    return category or family


def _amazon_job_url(job: dict[str, Any]) -> str:
    job_path = str(job.get("job_path") or "").strip()
    if not job_path:
        return ""
    if job_path.startswith("http://") or job_path.startswith("https://"):
        return job_path
    if job_path.startswith("/"):
        return f"{AMAZON_JOBS_BASE}{job_path}"
    return f"{AMAZON_JOBS_BASE}/{job_path}"


def fetch_amazon_search_raw(
    url: str,
    *,
    user_agent: str,
    timeout: int,
) -> str | None:
    """Fetch Amazon job-search results via ``search.json``, paginating by offset."""
    referer = url.split("?", 1)[0] if "?" in url else url
    session = requests.Session()
    all_jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_hits: int | None = None
    offset = 0

    for _page in range(MAX_PAGINATION_PAGES):
        api_url = amazon_search_json_url(
            url,
            offset=offset,
            result_limit=MAX_RESULT_LIMIT,
        )
        try:
            response = session.get(
                api_url,
                headers=_amazon_headers(user_agent, referer),
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
            logger.warning(
                "Amazon Jobs search fetch failed at offset %d: %s",
                offset,
                exc,
            )
            break

        if payload.get("error"):
            logger.warning("Amazon Jobs search API error: %s", payload["error"])
            break

        if total_hits is None:
            try:
                total_hits = int(payload.get("hits") or 0)
            except (TypeError, ValueError):
                total_hits = 0

        page_jobs = payload.get("jobs") or []
        if not isinstance(page_jobs, list) or not page_jobs:
            break

        for item in page_jobs:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id_icims") or "").strip()
            if job_id and job_id not in seen_ids:
                seen_ids.add(job_id)
                all_jobs.append(item)

        offset += MAX_RESULT_LIMIT
        if total_hits is not None and offset >= total_hits:
            break
        if len(page_jobs) < MAX_RESULT_LIMIT:
            break

        time.sleep(PAGE_FETCH_DELAY_SECONDS)

    if not all_jobs:
        return None

    return json.dumps({"jobs": all_jobs, "hits": len(all_jobs)})


def parse_amazon(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    """Parse Amazon Jobs ``search.json`` payload."""
    if isinstance(raw_json, dict):
        payload = raw_json
    else:
        payload = json.loads(raw_json)

    jobs = payload.get("jobs") or []
    if not isinstance(jobs, list):
        return []

    postings: list[JobPosting] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id_icims") or "").strip()
        title = str(job.get("title") or "").strip()
        if not job_id or not title:
            continue

        description = str(job.get("description_short") or job.get("description") or "")
        postings.append(
            JobPosting(
                id=job_id,
                title=title,
                department=_amazon_department(job),
                location=_amazon_location(job),
                url=_amazon_job_url(job),
                description=description,
                company_name=company_name,
            )
        )

    return postings
