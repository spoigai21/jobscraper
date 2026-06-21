from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from config import Settings
from models import AlertPayload, CompanyConfig, StateRecord

logger = logging.getLogger(__name__)

_MAX_FETCH_ATTEMPTS = 3
_FETCH_BACKOFF_SECONDS = 5
_STRIP_TAGS = ("script", "style", "nav", "footer", "header")


class CareerPageScraper:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch(self, url: str) -> str | None:
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
            except (
                requests.exceptions.HTTPError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException,
            ) as exc:
                logger.warning("Fetch failed for %s: %s", url, exc)
                return None
        return None

    def extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for tag_name in _STRIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        return soup.get_text(separator=" ", strip=True).lower()

    def hash_content(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def check_keywords(self, text: str, keywords: list[str]) -> str | None:
        for keyword in keywords:
            if keyword.lower() in text:
                return keyword
        return None

    def poll_company(
        self,
        company: CompanyConfig,
        state: StateRecord,
    ) -> AlertPayload | None:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        try:
            html = self.fetch(company.url)
            if html is None:
                state.last_checked = now_iso
                return None

            text = self.extract_text(html)
            content_hash = self.hash_content(text)
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
                        "Suppressing alert for %s: %.0fs since last (min %ds)",
                        company.name,
                        elapsed,
                        self._settings.min_alert_interval,
                    )
                    return None

            diff_snippet = "Page content changed"

            state.last_alerted = now_iso
            state.alert_count += 1
            logger.info(
                "Alert for %s keyword=%r count=%d",
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
