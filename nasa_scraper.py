"""NASA STEM Gateway (intern.nasa.gov) internship listing scraper."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from config import Settings
from job_parser import JobPosting, jobs_to_text

logger = logging.getLogger(__name__)

NASA_BASE_URL = "https://stemgateway.nasa.gov"
DEFAULT_LISTINGS_URL = f"{NASA_BASE_URL}/public/s/explore-opportunities"

NASA_COMPANY_NAMES: frozenset[str] = frozenset({"NASA", "JPL"})

_MAX_FETCH_ATTEMPTS = 3
_FETCH_BACKOFF_SECONDS = 5

# Software / engineering / CS internship filter terms.
_SWE_TERMS: tuple[str, ...] = (
    "software",
    "engineer",
    "engineering",
    "computer science",
    "developer",
    "programming",
    "information technology",
    "cybersecurity",
    "cyber security",
    "data science",
    "robotics",
    "aerospace engineering",
    "electrical engineering",
    "mechanical engineering",
    "computer engineering",
    "flight software",
    "embedded",
    "devops",
    "machine learning",
    "artificial intelligence",
)

_JPL_CENTER_TERMS: tuple[str, ...] = (
    "jpl",
    "jet propulsion laboratory",
)

_TAG_NOISE: frozenset[str] = frozenset(
    {
        "internship",
        "intern",
        "ostem",
        "summer",
        "spring",
        "fall",
        "winter",
        "2025",
        "2026",
        "2027",
    }
)

_OPPORTUNITY_LINK_MARKERS: tuple[str, ...] = (
    "course-offering",
    "opportunity",
    "engagement-opening",
)


def is_nasa_company(company_name: str) -> bool:
    """Return True when *company_name* should use the NASA scraper."""
    return company_name.strip() in NASA_COMPANY_NAMES


def is_swe_related(text: str) -> bool:
    """Return True when *text* looks software/engineering/CS related."""
    lowered = text.lower()
    return any(term in lowered for term in _SWE_TERMS)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _job_id_from_url(url: str, title: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path:
        slug = path.split("/")[-1]
        if slug and slug not in {"explore-opportunities", "opportunities", "s"}:
            return slug
    digest = hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()
    return digest[:16]


def _absolute_url(href: str, base_url: str) -> str:
    if not href:
        return base_url
    return urljoin(base_url, href)


def _extract_opportunity_url(card: Tag, base_url: str) -> str:
    for anchor in card.find_all("a", href=True):
        href = str(anchor["href"])
        if any(marker in href for marker in _OPPORTUNITY_LINK_MARKERS):
            return _absolute_url(href, base_url)
    title_link = card.select_one("h2 a[href], h3 a[href]")
    if title_link and title_link.get("href"):
        return _absolute_url(str(title_link["href"]), base_url)
    return base_url


def _extract_tags(card: Tag) -> list[str]:
    tags: list[str] = []
    for element in card.select(".slds-button_neutral, .slds-badge, .tag, .opportunity-tag"):
        text = _normalize_whitespace(element.get_text(" ", strip=True))
        if text and text.lower() not in _TAG_NOISE:
            tags.append(text)
    return tags


def _extract_description(card: Tag) -> str:
    for selector in (
        ".opportunity-description",
        ".slds-text-body_regular",
        "p.description",
        "p",
    ):
        node = card.select_one(selector)
        if node:
            text = _normalize_whitespace(node.get_text(" ", strip=True))
            if text:
                return text
    return _normalize_whitespace(card.get_text(" ", strip=True))


def _extract_title(card: Tag) -> str:
    for selector in ("h2", "h3", ".opportunity-title", ".slds-card__header-title"):
        node = card.select_one(selector)
        if node:
            text = _normalize_whitespace(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _location_from_tags(tags: list[str]) -> str:
    if not tags:
        return "NASA Center (see listing)"
    return ", ".join(tags)


def _matches_center_filter(text: str, center_filter: str | None) -> bool:
    if not center_filter:
        return True
    lowered = text.lower()
    if center_filter.upper() == "JPL":
        return any(term in lowered for term in _JPL_CENTER_TERMS)
    return center_filter.lower() in lowered


def parse_nasa_html(
    html: str,
    company_name: str,
    *,
    base_url: str = DEFAULT_LISTINGS_URL,
    center_filter: str | None = None,
    swe_only: bool = True,
) -> list[JobPosting]:
    """Parse NASA STEM Gateway opportunity cards from HTML.

    Handles Salesforce LWC card markup (``c-ostem_opportunityresultscard``)
    and a generic article-based fallback used in tests.
    """
    soup = BeautifulSoup(html, "lxml")
    cards: list[Tag] = list(soup.find_all("c-ostem_opportunityresultscard"))
    if not cards:
        cards = [
            article
            for article in soup.find_all("article")
            if article.find(["h2", "h3"])
        ]

    if center_filter is None and company_name.strip().upper() == "JPL":
        center_filter = "JPL"

    postings: list[JobPosting] = []
    for card in cards:
        title = _extract_title(card)
        if not title:
            continue

        tags = _extract_tags(card)
        description = _extract_description(card)
        url = _extract_opportunity_url(card, NASA_BASE_URL)
        location = _location_from_tags(tags)
        searchable = " ".join((title, location, description, " ".join(tags)))

        if swe_only and not is_swe_related(searchable):
            continue
        if not _matches_center_filter(searchable, center_filter):
            continue

        postings.append(
            JobPosting(
                id=_job_id_from_url(url, title),
                title=title,
                department="OSTEM Internship",
                location=location,
                url=url,
                description=description,
                company_name=company_name,
            )
        )

    return postings


def discover_listing_pages(html: str, base_url: str = DEFAULT_LISTINGS_URL) -> list[str]:
    """Return listing page URLs found in pagination or filter links."""
    soup = BeautifulSoup(html, "lxml")
    pages = {base_url}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if "explore-opportunities" in href:
            pages.add(_absolute_url(href, NASA_BASE_URL))
    return sorted(pages)


class NasaScraper:
    """Fetch and parse NASA STEM Gateway internship listings."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _request_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._settings.user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    def fetch(self, url: str) -> str | None:
        """Fetch raw HTML, retrying on transient connection errors."""
        headers = self._request_headers()
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
            except requests.exceptions.RequestException as exc:
                logger.warning("Request failed for %s: %s", url, exc)
                return None
        return None

    def fetch_listings(
        self,
        company_name: str = "NASA",
        *,
        url: str = DEFAULT_LISTINGS_URL,
        swe_only: bool = True,
    ) -> list[JobPosting]:
        """Fetch listing page(s) and return parsed SWE-related internships."""
        html = self.fetch(url)
        if html is None:
            return []

        pages = discover_listing_pages(html, url)
        seen_ids: set[str] = set()
        postings: list[JobPosting] = []

        for page_url in pages:
            page_html = html if page_url == url else self.fetch(page_url)
            if page_html is None:
                continue
            for job in parse_nasa_html(
                page_html,
                company_name,
                base_url=page_url,
                swe_only=swe_only,
            ):
                if job.id in seen_ids:
                    continue
                seen_ids.add(job.id)
                postings.append(job)

        if not postings:
            logger.debug(
                "No parseable NASA listings in HTML for %s (%d page(s) checked)",
                company_name,
                len(pages),
            )
        return postings


def nasa_jobs_to_text(jobs: list[JobPosting]) -> str:
    """Flatten parsed NASA jobs into searchable text."""
    return jobs_to_text(jobs)
