"""Meta Careers Comet GraphQL job search parser."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from monitor.models import JobPosting

logger = logging.getLogger(__name__)

META_CAREERS_BASE = "https://www.metacareers.com"
META_COMPANY_NAME = "Meta"

SEARCH_URL = f"{META_CAREERS_BASE}/jobsearch"
GRAPHQL_URL = f"{META_CAREERS_BASE}/api/graphql/"
JOBS_URL = f"{META_CAREERS_BASE}/jobs/{{job_id}}/"
MAX_META_PAGES = 10
DOC_ID = "29615178951461218"

FRIENDLY_NAME = "CareersJobSearchResultsDataQuery"
DEFAULT_SEARCH_QUERY = "intern"

_LSD_TOKEN_RE = re.compile(r'\["LSD",\[\],\{"token":"([^"]+)"')
_CLIENT_REVISION_RE = re.compile(r'"client_revision":(\d+)')
_HSI_RE = re.compile(r'"hsi":"(\d+)"')


def is_meta_company(company_name: str) -> bool:
    return company_name.strip() == META_COMPANY_NAME


def is_meta_jobs_url(url: str) -> bool:
    """Return True when *url* targets Meta Careers job search."""
    return "metacareers.com/jobsearch" in url.lower()


def meta_search_query(url: str) -> str:
    """Extract the search keyword from a Meta Careers job-search URL."""
    query = parse_qs(urlparse(url).query)
    values = query.get("q") or query.get("query") or [DEFAULT_SEARCH_QUERY]
    return values[0]


def _document_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


def _graphql_headers(user_agent: str, referer: str, lsd: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": META_CAREERS_BASE,
        "Referer": referer,
        "X-FB-LSD": lsd,
        "X-FB-Friendly-Name": FRIENDLY_NAME,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def _extract_token(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1) if match else ""


def _search_referer(term: str) -> str:
    return f"{SEARCH_URL}?{urlencode({'q': term})}"


def _search_input(term: str, page: int = 1) -> dict[str, Any]:
    return {
        "q": term,
        "divisions": [],
        "offices": [],
        "roles": [],
        "leadership_levels": [],
        "saved_jobs": [],
        "saved_searches": [],
        "sub_teams": [],
        "teams": [],
        "is_leadership": False,
        "is_remote_only": False,
        "sort_by_new": False,
        "page": page,
    }


def _decode_graphql_payload(text: str) -> dict[str, Any]:
    body = text.strip()
    if body.startswith("for (;;);"):
        body = body[len("for (;;);") :].strip()
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Meta Careers response was not a JSON object")
    if payload.get("errors"):
        raise ValueError(f"Meta Careers GraphQL error: {payload['errors']}")
    return payload


def _clean_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _extract_all_jobs(text: str) -> list[dict[str, Any]]:
    payload = _decode_graphql_payload(text)
    job_search = (payload.get("data") or {}).get("job_search_with_featured_jobs") or {}
    items = job_search.get("all_jobs") or []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def fetch_meta_search_raw(
    url: str,
    *,
    user_agent: str,
    timeout: int,
) -> str | None:
    """Fetch Meta job-search results via Comet GraphQL."""
    term = meta_search_query(url)
    referer = _search_referer(term)
    session = requests.Session()

    try:
        response = session.get(
            referer,
            headers=_document_headers(user_agent),
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.warning("Meta Careers search page fetch failed: %s", exc)
        return None

    lsd = _extract_token(_LSD_TOKEN_RE, response.text)
    if not lsd:
        logger.warning("Meta Careers LSD token not found in search page HTML")
        return None

    all_jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    client_revision = _extract_token(_CLIENT_REVISION_RE, response.text) or "0"
    hsi = _extract_token(_HSI_RE, response.text)

    for page in range(1, MAX_META_PAGES + 1):
        data = {
            "av": "0",
            "__user": "0",
            "__a": "1",
            "__req": "1",
            "__rev": client_revision,
            "__hsi": hsi,
            "__ccg": "GOOD",
            "__comet_req": "15",
            "lsd": lsd,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": FRIENDLY_NAME,
            "variables": json.dumps(
                {"search_input": _search_input(term, page)},
                separators=(",", ":"),
            ),
            "server_timestamps": "true",
            "doc_id": DOC_ID,
        }

        try:
            graphql_response = session.post(
                GRAPHQL_URL,
                data=data,
                headers=_graphql_headers(user_agent, referer, lsd),
                timeout=timeout,
            )
            graphql_response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.warning("Meta Careers GraphQL fetch failed on page %d: %s", page, exc)
            break

        page_jobs = _extract_all_jobs(graphql_response.text)
        if not page_jobs:
            break

        for item in page_jobs:
            job_id = str(item.get("id") or "").strip()
            if job_id and job_id not in seen_ids:
                seen_ids.add(job_id)
                all_jobs.append(item)

    if not all_jobs:
        return None

    return json.dumps(
        {
            "data": {
                "job_search_with_featured_jobs": {
                    "all_jobs": all_jobs,
                }
            }
        }
    )


def parse_meta(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    """Parse Meta Careers GraphQL ``job_search_with_featured_jobs`` payload."""
    if isinstance(raw_json, dict):
        payload = raw_json
    else:
        payload = _decode_graphql_payload(raw_json)

    job_search = (payload.get("data") or {}).get("job_search_with_featured_jobs") or {}
    items = job_search.get("all_jobs") or []
    if not isinstance(items, list):
        return []

    postings: list[JobPosting] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not job_id or not title:
            continue

        locations = _clean_string_list(item.get("locations"))
        teams = _clean_string_list(item.get("teams"))
        sub_teams = _clean_string_list(item.get("sub_teams"))
        roles = _clean_string_list(item.get("roles"))
        description_parts: list[str] = []
        if teams:
            description_parts.append(", ".join(teams))
        if sub_teams:
            description_parts.append(", ".join(sub_teams))
        if roles:
            description_parts.append(", ".join(roles))
        if locations:
            description_parts.append(", ".join(locations))

        postings.append(
            JobPosting(
                id=job_id,
                title=title,
                department=", ".join(teams),
                location=", ".join(locations),
                url=JOBS_URL.format(job_id=job_id),
                description="; ".join(description_parts),
                company_name=company_name,
            )
        )

    return postings
