"""ByteDance ATSX job search parser."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

from monitor.models import JobPosting

logger = logging.getLogger(__name__)

BYTEDANCE_CAREERS_BASE = "https://jobs.bytedance.com"
CSRF_URL = f"{BYTEDANCE_CAREERS_BASE}/api/v1/csrf/token"
SEARCH_URL = f"{BYTEDANCE_CAREERS_BASE}/api/v1/search/job/posts"
JOIN_BYTEDANCE_JOB_URL = "https://joinbytedance.com/search/{job_id}"
DEFAULT_SEARCH_KEYWORD = "intern"
DEFAULT_PORTAL_TYPE = 2
DEFAULT_PAGE_LIMIT = 100


def is_bytedance_jobs_url(url: str) -> bool:
    return "jobs.bytedance.com/api/v1/search/job/posts" in url.lower()


def bytedance_search_keyword(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    values = query.get("keyword") or query.get("q") or [DEFAULT_SEARCH_KEYWORD]
    return values[0]


def bytedance_portal_type(url: str) -> int:
    query = parse_qs(urlparse(url).query)
    values = query.get("portal_type") or [str(DEFAULT_PORTAL_TYPE)]
    try:
        return int(values[0])
    except (TypeError, ValueError):
        return DEFAULT_PORTAL_TYPE


def _bytedance_headers(user_agent: str, *, referer: str, csrf: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Origin": BYTEDANCE_CAREERS_BASE,
        "Referer": referer,
    }
    if csrf:
        headers["Content-Type"] = "application/json"
        headers["x-csrf-token"] = csrf
    return headers


def _bytedance_department(job: dict[str, Any]) -> str:
    category = job.get("job_category") or {}
    if isinstance(category, dict):
        en_name = category.get("en_name") or category.get("name")
        if en_name:
            return str(en_name)
    return ""


def _bytedance_location(job: dict[str, Any]) -> str:
    city_info = job.get("city_info") or {}
    if isinstance(city_info, dict):
        en_name = city_info.get("en_name") or city_info.get("name")
        if en_name:
            return str(en_name)
    city_list = job.get("city_list") or []
    if isinstance(city_list, list) and city_list:
        first = city_list[0]
        if isinstance(first, dict):
            en_name = first.get("en_name") or first.get("name")
            if en_name:
                return str(en_name)
    return ""


def _bytedance_job_url(job: dict[str, Any]) -> str:
    job_id = job.get("id")
    if job_id is not None:
        return JOIN_BYTEDANCE_JOB_URL.format(job_id=job_id)
    return ""


def fetch_bytedance_search_raw(
    url: str,
    *,
    user_agent: str,
    timeout: int,
) -> str | None:
    """Fetch ByteDance ATSX job search via CSRF-protected POST."""
    keyword = bytedance_search_keyword(url)
    portal_type = bytedance_portal_type(url)
    referer = f"{BYTEDANCE_CAREERS_BASE}/experienced/position"
    session = requests.Session()

    try:
        csrf_response = session.post(
            CSRF_URL,
            headers=_bytedance_headers(user_agent, referer=referer),
            data={"portal_entrance": "1"},
            timeout=timeout,
        )
        csrf_response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning("ByteDance CSRF token fetch failed: %s", exc)
        return None

    csrf: str | None = None
    try:
        token_payload = csrf_response.json()
        csrf = (token_payload.get("data") or {}).get("token")
    except (json.JSONDecodeError, AttributeError):
        csrf = None
    if not csrf:
        cookie_token = session.cookies.get("atsx-csrf-token")
        csrf = unquote(cookie_token) if cookie_token else None
    if not csrf:
        logger.warning("ByteDance CSRF token missing from response")
        return None

    payload = {
        "job_category_id_list": [],
        "keyword": keyword,
        "limit": DEFAULT_PAGE_LIMIT,
        "location_code_list": [],
        "offset": 0,
        "portal_entrance": 1,
        "portal_type": portal_type,
        "recruitment_id_list": [],
        "subject_id_list": [],
    }

    try:
        search_response = session.post(
            SEARCH_URL,
            headers=_bytedance_headers(user_agent, referer=referer, csrf=csrf),
            data=json.dumps(payload),
            timeout=timeout,
        )
        search_response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning("ByteDance job search fetch failed: %s", exc)
        return None

    return search_response.text


def parse_atsx_job_posts(
    raw_json: str | dict[str, Any],
    company_name: str,
    *,
    job_url_fn: Callable[[dict[str, Any]], str],
) -> list[JobPosting]:
    if isinstance(raw_json, dict):
        data = raw_json
    else:
        data = json.loads(raw_json)

    jobs = (data.get("data") or {}).get("job_post_list") or []
    if not isinstance(jobs, list):
        return []

    postings: list[JobPosting] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        title = str(job.get("title") or "").strip()
        if job_id is None or not title:
            continue
        description = str(job.get("description") or "")
        requirement = str(job.get("requirement") or "")
        if requirement:
            description = f"{description}\n{requirement}".strip()

        postings.append(
            JobPosting(
                id=str(job_id),
                title=title,
                department=_bytedance_department(job),
                location=_bytedance_location(job),
                url=job_url_fn(job),
                description=description,
                company_name=company_name,
            )
        )

    return postings


def parse_bytedance(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    return parse_atsx_job_posts(
        raw_json,
        company_name,
        job_url_fn=_bytedance_job_url,
    )
