"""Google Careers HiringCportalFrontendUi SSR parser."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from monitor.models import JobPosting

logger = logging.getLogger(__name__)

GOOGLE_JOBS_BASE = (
    "https://www.google.com/about/careers/applications/jobs/results"
)
MAX_PAGINATION_PAGES = 50
PAGE_FETCH_DELAY_SECONDS = 0.5

_DS1_CALLBACK_RE = re.compile(
    r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:(.*?)\}\);",
    re.DOTALL,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def is_google_careers_url(url: str) -> bool:
    """Return True when *url* targets Google Careers job search."""
    lowered = url.lower()
    return "careers.google.com/jobs" in lowered


def google_page_url(url: str, *, page: int) -> str:
    """Return *url* with ``page`` query parameter set."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page)]
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(query, doseq=True), "")
    )


def _google_headers(user_agent: str, referer: str) -> dict[str, str]:
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


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", text)).strip()


def _html_fragment(value: Any) -> str:
    if isinstance(value, list) and len(value) >= 2:
        text = value[1]
        if isinstance(text, str):
            return _strip_html(text)
    return ""


def _slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug


def _google_job_url(job_id: str, title: str) -> str:
    slug = _slugify(title)
    if slug:
        return f"{GOOGLE_JOBS_BASE}/{job_id}-{slug}/"
    return f"{GOOGLE_JOBS_BASE}/{job_id}/"


def _google_location(job: list[Any]) -> str:
    locations = job[9] if len(job) > 9 else None
    if not isinstance(locations, list):
        return ""
    names: list[str] = []
    for loc in locations:
        if isinstance(loc, list) and loc and isinstance(loc[0], str):
            name = loc[0].strip()
            if name:
                names.append(name)
    return "; ".join(names)


def _google_description(job: list[Any]) -> str:
    parts: list[str] = []
    for index in (3, 4, 10, 18, 19):
        if index >= len(job):
            continue
        fragment = _html_fragment(job[index])
        if fragment:
            parts.append(fragment)
    return "; ".join(parts)


def _google_job_id(job: list[Any]) -> str:
    return str(job[0] or "").strip() if job else ""


def _extract_ds1_jobs(html: str) -> list[list[Any]]:
    match = _DS1_CALLBACK_RE.search(html)
    if not match:
        return []

    data_str = match.group(1).strip()
    side_idx = data_str.find(", sideChannel:")
    if side_idx >= 0:
        data_str = data_str[:side_idx]

    try:
        payload = json.loads(data_str)
    except json.JSONDecodeError as exc:
        logger.warning("Google Careers ds:1 payload was not valid JSON: %s", exc)
        return []

    if not isinstance(payload, list) or not payload:
        return []

    jobs = payload[0]
    if not isinstance(jobs, list):
        return []

    return [job for job in jobs if isinstance(job, list)]


def _google_jobs_to_postings(
    jobs: list[list[Any]],
    company_name: str,
) -> list[JobPosting]:
    postings: list[JobPosting] = []

    for job in jobs:
        job_id = _google_job_id(job)
        title = str(job[1] or "").strip() if len(job) > 1 else ""
        if not job_id or not title:
            continue

        postings.append(
            JobPosting(
                id=job_id,
                title=title,
                department="",
                location=_google_location(job),
                url=_google_job_url(job_id, title),
                description=_google_description(job),
                company_name=company_name,
            )
        )

    return postings


def fetch_google_search_raw(
    url: str,
    *,
    user_agent: str,
    timeout: int,
) -> str | None:
    """Fetch Google Careers search results via paginated SSR HTML."""
    referer = url.split("?", 1)[0] if "?" in url else url
    session = requests.Session()
    all_jobs: list[list[Any]] = []
    seen_job_ids: set[str] = set()

    for page in range(1, MAX_PAGINATION_PAGES + 1):
        page_url = google_page_url(url, page=page)
        try:
            response = session.get(
                page_url,
                headers=_google_headers(user_agent, referer),
                timeout=timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.warning("Google Careers search fetch failed on page %d: %s", page, exc)
            break

        page_jobs = _extract_ds1_jobs(response.text)
        if not page_jobs:
            break

        new_on_page = 0
        for job in page_jobs:
            job_id = _google_job_id(job)
            if job_id and job_id not in seen_job_ids:
                seen_job_ids.add(job_id)
                all_jobs.append(job)
                new_on_page += 1

        if new_on_page == 0:
            break

        if page < MAX_PAGINATION_PAGES:
            time.sleep(PAGE_FETCH_DELAY_SECONDS)

    if not all_jobs:
        return None

    return json.dumps({"jobs": all_jobs})


def parse_google_html(html: str, company_name: str) -> list[JobPosting]:
    """Parse Google Careers SSR HTML embedded in ``AF_initDataCallback`` ds:1."""
    return _google_jobs_to_postings(_extract_ds1_jobs(html), company_name)


def parse_google(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    """Parse Google Careers paginated JSON or SSR HTML payload."""
    if isinstance(raw_json, dict):
        jobs = raw_json.get("jobs") or []
        if isinstance(jobs, list):
            return _google_jobs_to_postings(jobs, company_name)
        return []

    stripped = raw_json.lstrip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return parse_google_html(raw_json, company_name)
        jobs = payload.get("jobs") or []
        if isinstance(jobs, list):
            return _google_jobs_to_postings(jobs, company_name)
        return []

    return parse_google_html(raw_json, company_name)
