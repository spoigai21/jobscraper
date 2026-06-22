"""TikTok ATSX supplier job search parser."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from monitor.models import JobPosting
from monitor.parsers.bytedance import parse_atsx_job_posts

logger = logging.getLogger(__name__)

TIKTOK_CAREERS_BASE = "https://lifeattiktok.com"
TIKTOK_SEARCH_URL = (
    "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
)
DEFAULT_SEARCH_KEYWORD = "intern"
DEFAULT_PAGE_LIMIT = 100


def is_tiktok_jobs_url(url: str) -> bool:
    lowered = url.lower()
    return "api.lifeattiktok.com" in lowered and "/search/job/posts" in lowered


def tiktok_search_keyword(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    values = (
        query.get("keywords")
        or query.get("keyword")
        or query.get("q")
        or [DEFAULT_SEARCH_KEYWORD]
    )
    return values[0]


def _tiktok_job_url(job: dict[str, Any]) -> str:
    job_id = job.get("id")
    if job_id is not None:
        return f"{TIKTOK_CAREERS_BASE}/position/{job_id}"
    return ""


def _tiktok_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Accept-Language": "en",
        "Origin": TIKTOK_CAREERS_BASE,
        "website-path": "tiktok",
    }


def fetch_tiktok_search_raw(
    url: str,
    *,
    user_agent: str,
    timeout: int,
) -> str | None:
    """Fetch TikTok careers search via the public supplier API."""
    keyword = tiktok_search_keyword(url)
    payload = {
        "keywords": keyword,
        "limit": DEFAULT_PAGE_LIMIT,
        "offset": 0,
    }

    try:
        response = requests.post(
            TIKTOK_SEARCH_URL,
            headers=_tiktok_headers(user_agent),
            data=json.dumps(payload),
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning("TikTok job search fetch failed: %s", exc)
        return None

    return response.text


def parse_tiktok(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    return parse_atsx_job_posts(
        raw_json,
        company_name,
        job_url_fn=_tiktok_job_url,
    )
