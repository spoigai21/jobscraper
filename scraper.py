"""Careers page fetching, parsing, and change-detection for the internship monitor."""

from __future__ import annotations

import difflib
import hashlib
import logging
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import Settings
from models import AlertPayload, CompanyConfig, StateRecord

logger = logging.getLogger(__name__)

# Network retry policy for transient connection failures.
_MAX_FETCH_ATTEMPTS = 3
_FETCH_BACKOFF_SECONDS = 5

# Tags stripped before text extraction to reduce navigation/footer noise.
_STRIP_TAGS = ("script", "style", "nav", "footer", "header")


class CareerPageScraper:
    """Fetches company careers pages and detects keyword-relevant content changes."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the scraper with runtime settings (timeouts, user agent, etc.)."""
        self._settings = settings

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
        headers = {"User-Agent": self._settings.user_agent}

        for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
            try:
                response = requests.get(
                    url,
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

    def extract_text(self, html: str) -> str:
        """Extract normalized visible text from HTML.

        Parses with BeautifulSoup/lxml, removes script/style/nav/footer/header
        elements, and returns lowercased stripped plain text.

        Args:
            html: Raw HTML document.

        Returns:
            Normalized page text suitable for hashing and keyword search.
        """
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
            if keyword.lower() in lowered_text:
                return keyword
        return None

    def get_diff_snippet(self, old_text: str, new_text: str) -> str:
        """Summarize content added or changed between two text snapshots.

        Uses a sequence diff to collect insert/replace segments from ``new_text``
        that are not present in ``old_text``, then returns up to 300 characters.
        Falls back to a generic message when no novel snippet is found.

        Args:
            old_text: Previous normalized page text.
            new_text: Current normalized page text.

        Returns:
            A short human-readable snippet describing what changed.
        """
        matcher = difflib.SequenceMatcher(None, old_text, new_text)
        novel_parts: list[str] = []

        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
            if tag in ("insert", "replace"):
                novel_parts.append(new_text[j1:j2])

        snippet = " ".join(part.strip() for part in novel_parts if part.strip())
        if snippet:
            return snippet[:300]

        return "Page content changed"

    def poll_company(
        self,
        company: CompanyConfig,
        state: StateRecord,
    ) -> AlertPayload | None:
        """Poll a single company careers page and optionally emit an alert.

        Pipeline: fetch → extract text → hash → keyword check. Updates
        ``state.last_hash`` and ``state.last_checked`` on every successful parse.
        Emits an :class:`AlertPayload` only when the content hash changed, a
        keyword matched, and the minimum alert interval has elapsed since the
        last notification.

        Args:
            company: Company configuration (name, URL, keywords).
            state: Mutable persisted state for this company.

        Returns:
            An alert payload when all alert conditions are met, else ``None``.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        try:
            html = self.fetch(company.url)
            if html is None:
                state.last_checked = now_iso
                return None

            text = self.extract_text(html)
            content_hash = self.hash_content(text)

            # Preserve previous text hash before overwriting state for diffing.
            previous_hash = state.last_hash
            hash_changed = content_hash != previous_hash

            state.last_hash = content_hash
            state.last_checked = now_iso

            matched_keyword = self.check_keywords(text, company.keywords)
            if not hash_changed or matched_keyword is None:
                return None

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
                    return None

            # StateRecord stores hashes only, not prior text; use full new text
            # as the baseline on first observation, otherwise fall back to generic
            # messaging when a precise diff is unavailable.
            if not previous_hash:
                diff_snippet = self.get_diff_snippet("", text)
            else:
                diff_snippet = "Page content changed"

            state.last_alerted = now_iso
            state.alert_count += 1

            logger.info(
                "Alert triggered for %s (keyword=%r, alert_count=%d)",
                company.name,
                matched_keyword,
                state.alert_count,
            )

            return AlertPayload(
                company=company.name,
                url=company.url,
                trigger_keyword=matched_keyword,
                detected_at=now_iso,
                diff_snippet=diff_snippet,
            )
        except Exception:
            logger.exception("Unexpected error polling %s", company.name)
            state.last_checked = now_iso
            return None
