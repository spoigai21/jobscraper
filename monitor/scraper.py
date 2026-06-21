"""Careers page fetching, parsing, and change-detection for the internship monitor."""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from monitor.config import Settings
from monitor.parsers.boards import (
    BoardType,
    detect_board_type,
    job_matches_keyword,
    jobs_to_text,
    parse_job_board,
)
from monitor.parsers.nasa import is_nasa_company, nasa_jobs_to_text, parse_nasa_html
from monitor.models import AlertPayload, CompanyConfig, JobPosting, StateRecord
from monitor.profile import UserProfile
from monitor.scoring import classify_tier, score_job, should_exclude

logger = logging.getLogger(__name__)

# Network retry policy for transient connection failures.
_MAX_FETCH_ATTEMPTS = 3
_FETCH_BACKOFF_SECONDS = 5

# Tags stripped before text extraction to reduce navigation/footer noise.
_STRIP_TAGS = ("script", "style", "nav", "footer", "header")

# Minimum novel content length to treat a diff as substantial.
_MIN_SUBSTANTIAL_CHARS = 40

# Minimum line length for a non-keyword diff segment to be job-relevant.
_MIN_JOB_LINE_CHARS = 60

# Workday cxs job-search page size (API returns HTTP 400 when limit > 20).
_WORKDAY_REQUESTED_PAGE_LIMIT = 50
_WORKDAY_PAGE_LIMIT = 20

# Default job-related terms used when scanning diff segments.
_DEFAULT_JOB_TERMS: tuple[str, ...] = (
    "intern",
    "internship",
    "co-op",
    "co op",
    "co-op 2027",
    "spring 2027",
    "summer 2027",
    "fall 2027",
    "residency",
    "new grad",
    "early career",
)

# Boilerplate phrases commonly found in cookie/consent banners.
_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"cookie",
        r"privacy policy",
        r"terms of (use|service)",
        r"we use cookies",
        r"accept all",
        r"manage preferences",
        r"gdpr",
        r"ccpa",
        r"sign in",
        r"log in",
        r"subscribe",
    )
)


class CareerPageScraper:
    """Fetches company careers pages and detects keyword-relevant content changes."""

    def __init__(
        self,
        settings: Settings,
        profile: UserProfile | None = None,
    ) -> None:
        """Initialize the scraper with runtime settings (timeouts, user agent, etc.)."""
        self._settings = settings
        self._profile = profile

    def _request_headers(self, url: str, *, json_response: bool = False) -> dict[str, str]:
        """Build browser-like headers; job-board APIs request JSON."""
        headers = {
            "User-Agent": self._settings.user_agent,
            "Accept": (
                "application/json, text/plain, */*"
                if json_response
                else (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                )
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "empty" if json_response else "document",
            "Sec-Fetch-Mode": "cors" if json_response else "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        }
        if json_response:
            headers["Content-Type"] = "application/json"
        if not json_response:
            headers["Sec-Fetch-User"] = "?1"
        return headers

    @staticmethod
    def _is_per_job_board_url(url: str) -> bool:
        return detect_board_type(url) in (
            BoardType.GREENHOUSE,
            BoardType.ASHBY,
            BoardType.LEVER,
            BoardType.UBER,
            BoardType.WORKDAY,
        )

    @staticmethod
    def _load_seen_job_ids(state: StateRecord) -> set[str]:
        try:
            loaded = json.loads(state.seen_job_ids or "[]")
        except json.JSONDecodeError:
            return set()
        if not isinstance(loaded, list):
            return set()
        return {str(job_id) for job_id in loaded}

    @staticmethod
    def _save_seen_job_ids(state: StateRecord, job_ids: set[str]) -> None:
        state.seen_job_ids = json.dumps(sorted(job_ids))

    @staticmethod
    def _is_json_job_board_url(url: str) -> bool:
        lowered = url.lower()
        return any(
            marker in lowered
            for marker in (
                "boards-api.greenhouse.io",
                "api.ashbyhq.com/posting-api",
                "api.lever.co/v0/postings",
                "/wday/cxs/",
                "uber.com/api/loadsearchjobsresults",
            )
        )

    @staticmethod
    def _is_uber_jobs_api_url(url: str) -> bool:
        return "uber.com/api/loadsearchjobsresults" in url.lower()

    @staticmethod
    def _workday_search_text(url: str) -> str:
        query = parse_qs(urlparse(url).query)
        values = query.get("searchText") or query.get("q") or [""]
        return values[0]

    @staticmethod
    def _uber_search_query(url: str) -> str:
        query = parse_qs(urlparse(url).query)
        values = query.get("query") or query.get("q") or ["intern"]
        return values[0]

    @staticmethod
    def _uber_locale_code(url: str) -> str:
        query = parse_qs(urlparse(url).query)
        values = query.get("localeCode") or ["en"]
        return values[0]

    def _fetch_uber(self, url: str, headers: dict[str, str]) -> str:
        """POST to Uber's public careers search API (requires X-Csrf-Token)."""
        parsed = urlparse(url)
        request_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        locale_code = self._uber_locale_code(url)
        payload = {
            "params": {"query": self._uber_search_query(url)},
            "page": 0,
            "limit": 100,
        }
        uber_headers = {
            **headers,
            "X-Csrf-Token": "x",
            "Content-Type": "application/json",
        }
        response = requests.post(
            request_url,
            params={"localeCode": locale_code},
            headers=uber_headers,
            json=payload,
            timeout=self._settings.request_timeout,
        )
        response.raise_for_status()
        return response.text

    def _fetch_workday(self, url: str, headers: dict[str, str], request_url: str) -> str:
        """Paginate a Workday cxs job search and return aggregated JSON."""
        search_text = self._workday_search_text(url)
        page_limit = _WORKDAY_REQUESTED_PAGE_LIMIT
        all_postings: list[dict] = []
        total: int | None = None
        offset = 0

        while True:
            payload = {
                "appliedFacets": {},
                "limit": page_limit,
                "offset": offset,
                "searchText": search_text,
            }
            response = requests.post(
                request_url,
                headers=headers,
                json=payload,
                timeout=self._settings.request_timeout,
            )
            if response.status_code == 400 and page_limit > _WORKDAY_PAGE_LIMIT:
                page_limit = _WORKDAY_PAGE_LIMIT
                continue

            response.raise_for_status()
            data = response.json()

            if data.get("errorCode") and page_limit > _WORKDAY_PAGE_LIMIT:
                page_limit = _WORKDAY_PAGE_LIMIT
                continue

            postings = data.get("jobPostings") or []
            if total is None and isinstance(data.get("total"), int):
                total = data["total"]

            if not postings:
                break

            all_postings.extend(postings)

            if len(postings) < page_limit:
                break
            if total is not None and len(all_postings) >= total:
                break

            offset += page_limit

        return json.dumps(
            {
                "jobPostings": all_postings,
                "total": total if total is not None else len(all_postings),
            }
        )

    def _extract_text_from_json(self, raw: str, url: str) -> str:
        """Flatten public job-board JSON into searchable plain text."""
        board_type = detect_board_type(url)
        if board_type in (BoardType.GREENHOUSE, BoardType.ASHBY, BoardType.LEVER):
            jobs = parse_job_board(raw, url, "")
            return jobs_to_text(jobs)

        data = json.loads(raw)
        parts: list[str] = []
        lowered_url = url.lower()

        if "api.ashbyhq.com/posting-api" in lowered_url:
            for job in data.get("jobs", []):
                parts.extend(
                    str(job.get(field, ""))
                    for field in ("title", "department", "team", "employmentType", "location")
                )
        elif "boards-api.greenhouse.io" in lowered_url:
            for job in data.get("jobs", []):
                parts.append(str(job.get("title", "")))
                parts.append(str(job.get("content", "")))
                for dept in job.get("departments") or []:
                    if isinstance(dept, dict):
                        parts.append(str(dept.get("name", "")))
        elif "api.lever.co/v0/postings" in lowered_url:
            for job in data if isinstance(data, list) else []:
                parts.append(str(job.get("text", "")))
                categories = job.get("categories") or {}
                parts.extend(str(value) for value in categories.values())
        elif "/wday/cxs/" in lowered_url:
            for job in data.get("jobPostings", []):
                parts.append(str(job.get("title", "")))
                parts.append(str(job.get("locationsText", "")))
        elif "uber.com/api/loadsearchjobsresults" in lowered_url:
            jobs = parse_job_board(raw, url, "")
            return jobs_to_text(jobs)

        return " ".join(part for part in parts if part).lower()

    def fetch(self, url: str) -> str | None:
        """Fetch raw HTML from ``url``, retrying on connection errors.

        Uses the configured user agent and request timeout. Retries up to three
        times with a five-second pause between attempts when a connection error
        occurs. Logs warnings on failure and never raises.

        Args:
            url: Careers page URL to retrieve.

        Returns:
            Raw response body as a string, or ``None`` if all attempts fail.
        """
        json_board = self._is_json_job_board_url(url)
        headers = self._request_headers(url, json_response=json_board)
        request_url = url.split("?", 1)[0] if "/wday/cxs/" in url else url

        for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
            try:
                if "/wday/cxs/" in url:
                    return self._fetch_workday(url, headers, request_url)
                if self._is_uber_jobs_api_url(url):
                    return self._fetch_uber(url, headers)
                else:
                    response = requests.get(
                        request_url,
                        headers=headers,
                        timeout=self._settings.request_timeout,
                    )
                response.raise_for_status()
                return response.text
            except requests.exceptions.ConnectionError as exc:
                logger.warning(
                    "Connection error fetching %s (attempt %d/%d): %s",
                    url,
                    attempt,
                    _MAX_FETCH_ATTEMPTS,
                    exc,
                )
                if attempt < _MAX_FETCH_ATTEMPTS:
                    time.sleep(_FETCH_BACKOFF_SECONDS)
            except requests.exceptions.HTTPError as exc:
                logger.warning("HTTP error fetching %s: %s", url, exc)
                return None
            except requests.exceptions.Timeout as exc:
                logger.warning("Timeout fetching %s: %s", url, exc)
                return None
            except requests.exceptions.RequestException as exc:
                logger.warning("Request failed for %s: %s", url, exc)
                return None

        return None

    def extract_text(self, html: str, url: str = "") -> str:
        """Extract normalized visible text from HTML or job-board JSON.

        Parses with BeautifulSoup/lxml, removes script/style/nav/footer/header
        elements, and returns lowercased stripped plain text. Public Greenhouse,
        Ashby, Lever, and Workday JSON responses are flattened to plain text.

        Args:
            html: Raw HTML document or JSON payload.
            url: Source URL used to pick JSON parsing rules.

        Returns:
            Normalized page text suitable for hashing and keyword search.
        """
        stripped = html.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return self._extract_text_from_json(stripped, url)
            except json.JSONDecodeError:
                pass

        soup = BeautifulSoup(html, "lxml")

        for tag_name in _STRIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        return text.lower()

    def hash_content(self, text: str) -> str:
        """Compute a SHA-256 hex digest of normalized page text.

        Args:
            text: Normalized text from :meth:`extract_text`.

        Returns:
            Lowercase hexadecimal SHA-256 digest.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def check_keywords(self, text: str, keywords: list[str]) -> str | None:
        """Return the first keyword found in ``text`` (case-insensitive).

        Args:
            text: Normalized page text (typically already lowercased).
            keywords: Terms to search for, e.g. ``"intern"`` or ``"2027"``.

        Returns:
            The first matching keyword from ``keywords``, or ``None``.
        """
        lowered_text = text.lower()
        for keyword in keywords:
            lowered_keyword = keyword.lower()
            if lowered_keyword in {"intern", "2027"}:
                if re.search(rf"\b{re.escape(lowered_keyword)}\b", lowered_text):
                    return keyword
            elif lowered_keyword in lowered_text:
                return keyword
        return None

    def _normalize_diff_text(self, text: str) -> str:
        """Collapse whitespace and strip punctuation-only noise from diff text."""
        collapsed = re.sub(r"\s+", " ", text).strip()
        if not collapsed:
            return ""
        if re.fullmatch(r"[\W_]+", collapsed):
            return ""
        return collapsed

    def _is_boilerplate(self, text: str) -> bool:
        """Return True when *text* looks like cookie, nav, or consent boilerplate."""
        normalized = self._normalize_diff_text(text)
        if not normalized:
            return True
        return any(pattern.search(normalized) for pattern in _BOILERPLATE_PATTERNS)

    def _novel_diff_segments(self, old_text: str, new_text: str) -> list[str]:
        """Return normalized text segments present in *new_text* but not *old_text*."""
        matcher = difflib.SequenceMatcher(None, old_text, new_text)
        segments: list[str] = []

        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
            if tag not in ("insert", "replace"):
                continue
            segment = self._normalize_diff_text(new_text[j1:j2])
            if segment and not self._is_boilerplate(segment):
                segments.append(segment)

        return segments

    def _job_search_terms(self, keywords: list[str]) -> tuple[str, ...]:
        """Merge configured keywords with default internship-related terms."""
        merged = {term.lower() for term in keywords}
        merged.update(_DEFAULT_JOB_TERMS)
        return tuple(sorted(merged))

    def _contains_job_term(self, text: str, job_terms: tuple[str, ...]) -> bool:
        """Return True when *text* contains an internship-related search term."""
        lowered = text.lower()
        return any(term in lowered for term in job_terms)

    def _find_job_snippet(
        self,
        old_text: str,
        new_text: str,
        keywords: list[str],
    ) -> str | None:
        """Return the best job-related snippet from a page diff, if any."""
        job_terms = self._job_search_terms(keywords)
        candidates: list[str] = []

        for segment in self._novel_diff_segments(old_text, new_text):
            if self._contains_job_term(segment, job_terms):
                candidates.append(segment)
            elif len(segment) >= _MIN_JOB_LINE_CHARS:
                candidates.append(segment)

        if not candidates:
            return None

        candidates.sort(key=len, reverse=True)
        return candidates[0]

    def _is_substantial_change(
        self,
        old_text: str,
        new_text: str,
        job_snippet: str | None,
    ) -> bool:
        """Return True when the diff contains meaningful new content."""
        if job_snippet:
            return True

        segments = self._novel_diff_segments(old_text, new_text)
        if not segments:
            return False

        total_chars = sum(len(segment) for segment in segments)
        return total_chars >= _MIN_SUBSTANTIAL_CHARS

    def get_diff_snippet(
        self,
        old_text: str,
        new_text: str,
        keywords: list[str] | None = None,
    ) -> str:
        """Summarize job-relevant content added between two text snapshots.

        Prefers internship-related diff segments; falls back to the largest
        non-boilerplate addition. Returns up to 300 characters.

        Args:
            old_text: Previous normalized page text.
            new_text: Current normalized page text.
            keywords: Optional configured keywords for job-term detection.

        Returns:
            A short human-readable snippet describing what changed.
        """
        keywords = keywords or []
        job_snippet = self._find_job_snippet(old_text, new_text, keywords)
        if job_snippet:
            return f"New: {job_snippet[:280]}"

        segments = self._novel_diff_segments(old_text, new_text)
        if segments:
            segments.sort(key=len, reverse=True)
            return f"New: {segments[0][:280]}"

        return "Page content changed"

    def _build_job_alert(
        self,
        job: JobPosting,
        company: CompanyConfig,
        now_iso: str,
    ) -> AlertPayload | None:
        """Score a single new job and build an alert payload when it qualifies."""
        trigger_keyword = job_matches_keyword(job, company.keywords)
        if trigger_keyword is None:
            return None

        if self._profile is not None and should_exclude(job, self._profile):
            logger.debug(
                "Excluding %s at %s (%r)",
                job.title,
                company.name,
                job.id,
            )
            return None

        score = score_job(job, self._profile) if self._profile is not None else 0
        tier = (
            classify_tier(score, self._profile)
            if self._profile is not None
            else "standard"
        )
        job_url = job.url or company.url
        meta = ", ".join(part for part in (job.department, job.location) if part)
        diff_snippet = f"New: {job.title}"
        if meta:
            diff_snippet = f"{diff_snippet} ({meta})"

        return AlertPayload(
            company=company.name,
            url=job_url,
            job_title=job.title,
            job_url=job_url,
            relevance_score=score,
            tier=tier,
            trigger_keyword=trigger_keyword,
            detected_at=now_iso,
            diff_snippet=diff_snippet[:300],
        )

    def _poll_per_job_board(
        self,
        company: CompanyConfig,
        state: StateRecord,
        raw: str,
        now: datetime,
        now_iso: str,
    ) -> list[AlertPayload]:
        """Detect new listings on Greenhouse, Ashby, or Lever JSON boards."""
        jobs = parse_job_board(raw, company.url, company.name)
        current_ids = {job.id for job in jobs}
        seen_ids = self._load_seen_job_ids(state)

        text = jobs_to_text(jobs)
        state.last_hash = self.hash_content(text)
        state.last_text = text
        state.last_checked = now_iso

        if not seen_ids:
            self._save_seen_job_ids(state, current_ids)
            logger.debug(
                "Seeding job IDs for %s (%d listings)",
                company.name,
                len(current_ids),
            )
            return []

        new_jobs = [job for job in jobs if job.id not in seen_ids]
        self._save_seen_job_ids(state, current_ids)

        if not new_jobs:
            return []

        alerts = [
            payload
            for job in new_jobs
            if (payload := self._build_job_alert(job, company, now_iso)) is not None
        ]
        if not alerts:
            logger.debug(
                "Ignoring %d new listings for %s (filtered out)",
                len(new_jobs),
                company.name,
            )
            return []

        if state.last_alerted is not None:
            last_alerted = datetime.fromisoformat(state.last_alerted)
            elapsed = (now - last_alerted).total_seconds()
            if elapsed <= self._settings.min_alert_interval:
                logger.info(
                    "Suppressing alert for %s: %.0fs since last alert "
                    "(min interval %ds)",
                    company.name,
                    elapsed,
                    self._settings.min_alert_interval,
                )
                return []

        state.last_alerted = now_iso
        state.alert_count += len(alerts)

        for payload in alerts:
            logger.info(
                "Alert triggered for %s (%r, score=%d, tier=%s)",
                company.name,
                payload.job_title or payload.trigger_keyword,
                payload.relevance_score,
                payload.tier,
            )

        return alerts

    def _poll_nasa(
        self,
        company: CompanyConfig,
        state: StateRecord,
        now: datetime,
        now_iso: str,
    ) -> list[AlertPayload]:
        """Detect new SWE-related listings on NASA STEM Gateway."""
        html = self.fetch(company.url)
        if html is None:
            state.last_checked = now_iso
            return []

        jobs = parse_nasa_html(html, company.name, base_url=company.url)
        current_ids = {job.id for job in jobs}
        seen_ids = self._load_seen_job_ids(state)

        text = nasa_jobs_to_text(jobs)
        state.last_hash = self.hash_content(text)
        state.last_text = text
        state.last_checked = now_iso

        if not seen_ids:
            self._save_seen_job_ids(state, current_ids)
            logger.debug(
                "Seeding NASA job IDs for %s (%d listings)",
                company.name,
                len(current_ids),
            )
            return []

        new_jobs = [job for job in jobs if job.id not in seen_ids]
        self._save_seen_job_ids(state, current_ids)

        if not new_jobs:
            return []

        alerts = [
            payload
            for job in new_jobs
            if (payload := self._build_job_alert(job, company, now_iso)) is not None
        ]
        if not alerts:
            logger.debug(
                "Ignoring %d new NASA listings for %s (filtered out)",
                len(new_jobs),
                company.name,
            )
            return []

        if state.last_alerted is not None:
            last_alerted = datetime.fromisoformat(state.last_alerted)
            elapsed = (now - last_alerted).total_seconds()
            if elapsed <= self._settings.min_alert_interval:
                logger.info(
                    "Suppressing alert for %s: %.0fs since last alert "
                    "(min interval %ds)",
                    company.name,
                    elapsed,
                    self._settings.min_alert_interval,
                )
                return []

        state.last_alerted = now_iso
        state.alert_count += len(alerts)

        for payload in alerts:
            logger.info(
                "Alert triggered for %s (%r, score=%d, tier=%s)",
                company.name,
                payload.job_title or payload.trigger_keyword,
                payload.relevance_score,
                payload.tier,
            )

        return alerts

    def poll_company(
        self,
        company: CompanyConfig,
        state: StateRecord,
    ) -> list[AlertPayload]:
        """Poll a single company careers page and optionally emit alerts.

        JSON boards (Greenhouse/Ashby/Lever): fetch → parse jobs → diff IDs →
        score/filter each new job → emit per-job alerts.

        HTML fallback: fetch → hash diff → keyword check (legacy path).

        Args:
            company: Company configuration (name, URL, keywords).
            state: Mutable persisted state for this company.

        Returns:
            Zero or more alert payloads for newly detected qualifying jobs.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        try:
            if is_nasa_company(company.name):
                return self._poll_nasa(company, state, now, now_iso)

            html = self.fetch(company.url)
            if html is None:
                state.last_checked = now_iso
                return []

            if self._is_per_job_board_url(company.url):
                return self._poll_per_job_board(company, state, html, now, now_iso)

            text = self.extract_text(html, company.url)
            content_hash = self.hash_content(text)

            previous_text = state.last_text or ""
            previous_hash = state.last_hash
            hash_changed = content_hash != previous_hash

            state.last_hash = content_hash
            state.last_text = text
            state.last_checked = now_iso

            if not hash_changed:
                return []

            # First successful poll seeds baseline text without alerting.
            if not previous_hash:
                logger.debug(
                    "Seeding baseline for %s (hash=%s…)",
                    company.name,
                    content_hash[:8],
                )
                return []

            job_snippet = self._find_job_snippet(previous_text, text, company.keywords)
            matched_keyword = self.check_keywords(text, company.keywords)
            if matched_keyword is None and not self._is_substantial_change(
                previous_text, text, job_snippet
            ):
                logger.debug(
                    "Ignoring trivial change for %s (no substantial diff)",
                    company.name,
                )
                return []

            if matched_keyword is None and job_snippet is None:
                return []

            if state.last_alerted is not None:
                last_alerted = datetime.fromisoformat(state.last_alerted)
                elapsed = (now - last_alerted).total_seconds()
                if elapsed <= self._settings.min_alert_interval:
                    logger.info(
                        "Suppressing alert for %s: %.0fs since last alert "
                        "(min interval %ds)",
                        company.name,
                        elapsed,
                        self._settings.min_alert_interval,
                    )
                    return []

            diff_snippet = self.get_diff_snippet(
                previous_text,
                text,
                company.keywords,
            )
            trigger_keyword = matched_keyword or "job listing"

            state.last_alerted = now_iso
            state.alert_count += 1

            logger.info(
                "Alert triggered for %s (keyword=%r, alert_count=%d)",
                company.name,
                trigger_keyword,
                state.alert_count,
            )

            return [
                AlertPayload(
                    company=company.name,
                    url=company.url,
                    trigger_keyword=trigger_keyword,
                    detected_at=now_iso,
                    diff_snippet=diff_snippet,
                )
            ]
        except Exception:
            logger.exception("Unexpected error polling %s", company.name)
            state.last_checked = now_iso
            return []
