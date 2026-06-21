"""Tesla careers (cua-api state) parser.

Tesla's careers JSON is served from ``/cua-api/apps/careers/state`` (and mirror
paths) behind Akamai Bot Manager. Datacenter IPs typically get HTTP 403/429 or
an Akamai challenge page instead of listings JSON. ``TeslaScraper`` warms a
session on the careers search page, tries several state/search endpoints with
browser-like headers, and optionally uses ``curl_cffi`` TLS impersonation when
installed. Monitoring stays disabled in ``companies.py`` until live fetch returns
valid state JSON from the deployment environment.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from monitor.config import Settings
from monitor.models import JobPosting
from monitor.parsers.boards import jobs_to_text

logger = logging.getLogger(__name__)

TESLA_STATE_API = "https://www.tesla.com/cua-api/apps/careers/state"
TESLA_STATE_ALT_API = "https://www.tesla.com/careers/search/state"
TESLA_SEARCH_API = "https://www.tesla.com/cua-api/careers/search"
TESLA_CAREERS_BASE = "https://www.tesla.com"
TESLA_COMPANY_NAME = "Tesla"
_TESLA_STATE_ENDPOINTS = (TESLA_STATE_API, TESLA_STATE_ALT_API)

_MAX_FETCH_ATTEMPTS = 3
_FETCH_BACKOFF_SECONDS = 5


def is_tesla_company(company_name: str) -> bool:
    return company_name.strip() == TESLA_COMPANY_NAME


def is_tesla_search_url(url: str) -> bool:
    lowered = url.lower()
    return "tesla.com/cua-api" in lowered or "tesla.com/careers/search" in lowered


def _load_json(raw_json: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_json, dict):
        return raw_json
    loaded = json.loads(raw_json)
    return loaded if isinstance(loaded, dict) else {}


def _slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "job"


def _tesla_url(title: str, job_id: str) -> str:
    slug = _slugify_title(title)
    return f"{TESLA_CAREERS_BASE}/careers/search/job/{slug}-{job_id}"


def _lookup_value(lookup: dict[str, Any], bucket: str, key: Any) -> str:
    table = lookup.get(bucket)
    if not isinstance(table, dict):
        return ""
    value = table.get(str(key))
    return str(value) if value is not None else ""


def _site_location_ids(data: dict[str, Any], site: str) -> set[str]:
    location_ids: set[str] = set()
    for geo_entry in data.get("geo") or []:
        if not isinstance(geo_entry, dict):
            continue
        for site_entry in geo_entry.get("sites") or []:
            if not isinstance(site_entry, dict):
                continue
            if str(site_entry.get("id") or "") != site:
                continue
            cities = site_entry.get("cities")
            if isinstance(cities, dict):
                for city_locations in cities.values():
                    if isinstance(city_locations, list):
                        location_ids.update(str(item) for item in city_locations)
    return location_ids


def _source_params(source_url: str) -> dict[str, str]:
    query = parse_qs(urlparse(source_url).query)
    return {key: values[0] for key, values in query.items() if values}


def _listing_title(job: dict[str, Any]) -> str:
    return str(job.get("t") or job.get("title") or job.get("name") or "")


def _listing_department(job: dict[str, Any], lookup: dict[str, Any]) -> str:
    dept_key = job.get("dp") if job.get("dp") is not None else job.get("d")
    if dept_key is None:
        return str(job.get("department") or job.get("team") or "")
    resolved = _lookup_value(lookup, "departments", dept_key)
    return resolved or str(dept_key)


def _listing_location(job: dict[str, Any], lookup: dict[str, Any]) -> str:
    location_key = job.get("l")
    if location_key is None:
        return str(job.get("location") or job.get("locationName") or "")
    return _lookup_value(lookup, "locations", location_key) or str(location_key)


def _listing_type(job: dict[str, Any], lookup: dict[str, Any]) -> str:
    type_key = job.get("y")
    if type_key is None:
        return str(job.get("type") or job.get("employmentType") or "")
    return _lookup_value(lookup, "types", type_key) or str(type_key)


def _matches_filters(
    job: dict[str, Any],
    lookup: dict[str, Any],
    *,
    source_url: str,
    data: dict[str, Any],
) -> bool:
    params = _source_params(source_url)
    title = _listing_title(job)
    lowered_title = title.lower()

    type_param = params.get("type")
    if type_param:
        listing_type = _listing_type(job, lookup).lower()
        type_values = lookup.get("types")
        expected = ""
        if isinstance(type_values, dict):
            expected = str(type_values.get(type_param) or type_param).lower()
        else:
            expected = type_param.lower()
        if listing_type and listing_type != expected:
            return False

    query = params.get("query", "").lower()
    if query and query not in lowered_title:
        return False

    site = params.get("site")
    if site:
        allowed_locations = _site_location_ids(data, site)
        if allowed_locations:
            location_key = str(job.get("l") or "")
            if location_key and location_key not in allowed_locations:
                return False

    return bool(title)


def parse_tesla_state(
    raw_json: str | dict[str, Any],
    company_name: str,
    *,
    source_url: str = "",
) -> list[JobPosting]:
    """Parse Tesla careers state JSON (abbreviated listing keys)."""
    data = _load_json(raw_json)
    lookup = data.get("lookup") if isinstance(data.get("lookup"), dict) else {}
    listings = data.get("listings") or []
    postings: list[JobPosting] = []

    for job in listings:
        if not isinstance(job, dict):
            continue
        if source_url and not _matches_filters(job, lookup, source_url=source_url, data=data):
            continue
        job_id = job.get("id")
        if job_id is None:
            continue
        title = _listing_title(job)
        postings.append(
            JobPosting(
                id=str(job_id),
                title=title,
                department=_listing_department(job, lookup),
                location=_listing_location(job, lookup),
                url=_tesla_url(title, str(job_id)),
                description=str(job.get("description") or job.get("summary") or ""),
                company_name=company_name,
            )
        )

    return postings


def parse_tesla(raw_json: str | dict[str, Any], company_name: str) -> list[JobPosting]:
    """Parse Tesla careers search JSON (non-state endpoints)."""
    data = _load_json(raw_json)
    postings: list[JobPosting] = []

    listings = data.get("listings")
    if isinstance(listings, list):
        return parse_tesla_state(data, company_name)

    for key in ("jobs", "results", "positions"):
        value = data.get(key)
        if not isinstance(value, list):
            continue
        for job in value:
            if not isinstance(job, dict):
                continue
            job_id = job.get("id") or job.get("jobId")
            if job_id is None:
                continue
            title = str(job.get("title") or job.get("name") or job.get("text") or "")
            postings.append(
                JobPosting(
                    id=str(job_id),
                    title=title,
                    department=str(job.get("department") or job.get("team") or ""),
                    location=str(job.get("location") or ""),
                    url=_tesla_url(title, str(job_id)),
                    description=str(job.get("description") or ""),
                    company_name=company_name,
                )
            )
        break

    return postings


def tesla_jobs_to_text(jobs: list[JobPosting]) -> str:
    return jobs_to_text(jobs)


def _default_referer(source_url: str = "") -> str:
    return source_url or f"{TESLA_CAREERS_BASE}/careers/search/?type=3&query=intern"


def _browser_headers(user_agent: str, *, referer: str = "", json_api: bool = True) -> dict[str, str]:
    resolved_referer = referer or f"{TESLA_CAREERS_BASE}/careers/search/"
    headers = {
        "User-Agent": user_agent,
        "Accept": (
            "application/json, text/plain, */*"
            if json_api
            else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": resolved_referer,
        "Origin": TESLA_CAREERS_BASE,
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document" if not json_api else "empty",
        "Sec-Fetch-Mode": "navigate" if not json_api else "cors",
        "Sec-Fetch-Site": "none" if not json_api else "same-origin",
    }
    if not json_api:
        headers["Upgrade-Insecure-Requests"] = "1"
    return headers


def _search_api_url(source_url: str) -> str:
    params = _source_params(source_url)
    if not params:
        return TESLA_SEARCH_API
    query = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
    return f"{TESLA_SEARCH_API}?{query}"


def _is_valid_state_payload(raw_text: str) -> bool:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return isinstance(data.get("listings"), list)


def _is_blocked_response(raw_text: str, status_code: int) -> bool:
    if status_code in (403, 429):
        return True
    stripped = raw_text.strip()
    if not stripped:
        return True
    if stripped.startswith("<"):
        lowered = stripped.lower()
        return any(
            marker in lowered
            for marker in ("access denied", "sec-if-cpt-container", "akamai")
        )
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return True
        if isinstance(payload, dict) and payload.get("cpr_chlge"):
            return True
    return False


def _fetch_with_curl_cffi(
    url: str,
    *,
    referer: str,
    user_agent: str,
    timeout: int,
) -> tuple[int, str] | None:
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return None

    headers = _browser_headers(user_agent, referer=referer, json_api=True)
    try:
        response = curl_requests.get(
            url,
            headers=headers,
            impersonate="chrome120",
            timeout=timeout,
        )
    except Exception as exc:
        logger.debug("curl_cffi fetch failed for %s: %s", url, exc)
        return None
    return response.status_code, response.text


class TeslaScraper:
    """Fetch Tesla careers state JSON."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _warmup_session(self, session: requests.Session, referer: str) -> None:
        try:
            session.get(
                referer,
                headers=_browser_headers(
                    self._settings.user_agent,
                    referer=referer,
                    json_api=False,
                ),
                timeout=self._settings.request_timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("Tesla careers page warmup failed: %s", exc)

    def _try_endpoint(
        self,
        session: requests.Session,
        url: str,
        *,
        referer: str,
    ) -> str | None:
        headers = _browser_headers(self._settings.user_agent, referer=referer, json_api=True)
        try:
            response = session.get(
                url,
                headers=headers,
                timeout=self._settings.request_timeout,
            )
        except requests.exceptions.ConnectionError:
            raise
        except requests.exceptions.RequestException as exc:
            logger.debug("Tesla endpoint request failed for %s: %s", url, exc)
            return None

        if _is_blocked_response(response.text, response.status_code):
            logger.debug(
                "Tesla endpoint blocked for %s (HTTP %s)",
                url,
                response.status_code,
            )
            return None
        if not _is_valid_state_payload(response.text):
            logger.debug("Tesla endpoint returned non-state JSON for %s", url)
            return None
        return response.text

    def _fetch_endpoints_once(self, referer: str) -> str | None:
        session = requests.Session()
        self._warmup_session(session, referer)

        for url in _TESLA_STATE_ENDPOINTS:
            try:
                raw = self._try_endpoint(session, url, referer=referer)
            except requests.exceptions.ConnectionError:
                raise
            if raw is not None:
                return raw

        search_url = _search_api_url(referer)
        try:
            raw = self._try_endpoint(session, search_url, referer=referer)
        except requests.exceptions.ConnectionError:
            raise
        if raw is not None:
            return raw

        for url in (*_TESLA_STATE_ENDPOINTS, search_url):
            curl_result = _fetch_with_curl_cffi(
                url,
                referer=referer,
                user_agent=self._settings.user_agent,
                timeout=self._settings.request_timeout,
            )
            if curl_result is None:
                continue
            status_code, raw_text = curl_result
            if _is_blocked_response(raw_text, status_code):
                continue
            if _is_valid_state_payload(raw_text):
                return raw_text

        return None

    def fetch_state(self, source_url: str = "") -> str | None:
        """Fetch raw careers state JSON, retrying on connection errors."""
        referer = _default_referer(source_url)

        for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
            try:
                raw = self._fetch_endpoints_once(referer)
                if raw is not None:
                    return raw
            except requests.exceptions.ConnectionError as exc:
                logger.warning(
                    "Connection error fetching Tesla state (attempt %d/%d): %s",
                    attempt,
                    _MAX_FETCH_ATTEMPTS,
                    exc,
                )
                if attempt < _MAX_FETCH_ATTEMPTS:
                    time.sleep(_FETCH_BACKOFF_SECONDS)
                    continue

            logger.warning(
                "Tesla careers state fetch blocked or empty (attempt %d/%d)",
                attempt,
                _MAX_FETCH_ATTEMPTS,
            )
            if attempt < _MAX_FETCH_ATTEMPTS:
                time.sleep(_FETCH_BACKOFF_SECONDS)

        return None

    def fetch_listings(
        self,
        company_name: str = TESLA_COMPANY_NAME,
        *,
        source_url: str = "",
    ) -> list[JobPosting]:
        raw = self.fetch_state(source_url)
        if raw is None:
            return []
        return parse_tesla_state(raw, company_name, source_url=source_url)
