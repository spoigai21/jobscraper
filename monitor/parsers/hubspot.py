"""HubSpot careers GraphQL job board parser."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any

import requests

from monitor.models import JobPosting

logger = logging.getLogger(__name__)

HUBSPOT_CAREERS_BASE = "https://www.hubspot.com/careers/jobs"
GRAPHQL_URL = "https://wtcfns.hubspot.com/careers/graphql"

_JOBS_QUERY = """query Jobs {
  jobs {
    id
    title
    absolute_url
    department { name }
    location { name }
    content
  }
}"""

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def is_hubspot_jobs_url(url: str) -> bool:
    """Return True when *url* targets HubSpot careers GraphQL."""
    lowered = url.lower()
    return "wtcfns.hubspot.com/careers/graphql" in lowered


def _strip_html(text: str) -> str:
    if not text:
        return ""
    decoded = html.unescape(text)
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", decoded)).strip()


def _graphql_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Referer": HUBSPOT_CAREERS_BASE,
    }


def fetch_hubspot_jobs_raw(
    url: str,
    *,
    user_agent: str,
    timeout: int,
) -> str | None:
    """Fetch all HubSpot job postings via careers GraphQL."""
    del url  # GraphQL endpoint is fixed; company URL is for detect_board_type only.
    body = {
        "operationName": "Jobs",
        "query": _JOBS_QUERY,
    }
    try:
        response = requests.post(
            GRAPHQL_URL,
            json=body,
            headers=_graphql_headers(user_agent),
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning("HubSpot careers GraphQL fetch failed: %s", exc)
        return None

    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError:
        logger.warning("HubSpot careers GraphQL response was not JSON")
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("errors"):
        logger.warning("HubSpot careers GraphQL error: %s", payload["errors"])
        return None
    jobs = (payload.get("data") or {}).get("jobs")
    if not isinstance(jobs, list) or not jobs:
        return None

    return response.text


def parse_hubspot(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    """Parse HubSpot careers GraphQL ``jobs`` payload."""
    if isinstance(raw_json, dict):
        payload = raw_json
    else:
        payload = json.loads(raw_json)

    jobs = (payload.get("data") or {}).get("jobs") or []
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

        department = job.get("department") or {}
        location = job.get("location") or {}
        dept_name = str(department.get("name") or "") if isinstance(department, dict) else ""
        loc_name = str(location.get("name") or "") if isinstance(location, dict) else ""
        job_url = str(job.get("absolute_url") or f"{HUBSPOT_CAREERS_BASE}/{job_id}")

        postings.append(
            JobPosting(
                id=str(job_id),
                title=title,
                department=dept_name,
                location=loc_name,
                url=job_url,
                description=_strip_html(str(job.get("content") or "")),
                company_name=company_name,
            )
        )

    return postings
