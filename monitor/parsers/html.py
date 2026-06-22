"""Parse job listings from HTML career pages (Lever, Greenhouse embeds, generic cards)."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from monitor.models import JobPosting
from monitor.parsers.boards import _strip_html

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _job_id_from_url(url: str, title: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path:
        slug = path.split("/")[-1]
        if slug and slug not in {"careers", "jobs", "search", "openings"}:
            return slug
    digest = hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()
    return digest[:16]


def _absolute_url(href: str, base_url: str) -> str:
    if not href:
        return base_url
    return urljoin(base_url, href)


def _text_from_node(node: Tag | None) -> str:
    if node is None:
        return ""
    return _normalize_whitespace(node.get_text(" ", strip=True))


def _description_from_card(card: Tag) -> str:
    for selector in (
        ".posting-description",
        ".job-description",
        ".opening-description",
        ".opportunity-description",
        ".slds-text-body_regular",
        "[class*='description']",
        "p",
    ):
        node = card.select_one(selector)
        if node is None:
            continue
        text = _text_from_node(node)
        if text and len(text) > 20:
            return text
    return ""


def _parse_lever_postings(
    soup: BeautifulSoup,
    company_name: str,
    base_url: str,
) -> list[JobPosting]:
    postings: list[JobPosting] = []
    for card in soup.select(".posting"):
        title_node = card.select_one(".posting-title h5, .posting-title, h5")
        title = _text_from_node(title_node)
        if not title:
            continue

        link = card.select_one("a.posting-title[href], a[href][class*='posting']")
        job_url = _absolute_url(str(link["href"]) if link and link.get("href") else "", base_url)

        categories = [
            _text_from_node(span)
            for span in card.select(".posting-categories span, .sort-by-team .posting-category")
        ]
        categories = [value for value in categories if value]
        department = categories[0] if categories else ""
        location = categories[1] if len(categories) > 1 else ""
        commitment = categories[2] if len(categories) > 2 else ""

        description_parts = [_description_from_card(card)]
        if commitment:
            description_parts.append(commitment)
        description = "; ".join(part for part in description_parts if part)

        job_id = str(card.get("data-qa-posting-id") or "") or _job_id_from_url(job_url, title)
        postings.append(
            JobPosting(
                id=job_id,
                title=title,
                department=department,
                location=location,
                url=job_url,
                description=description,
                company_name=company_name,
            )
        )
    return postings


def _parse_greenhouse_openings(
    soup: BeautifulSoup,
    company_name: str,
    base_url: str,
) -> list[JobPosting]:
    postings: list[JobPosting] = []
    for card in soup.select(".opening, [data-mapped-job-id], .job-post"):
        title_node = card.select_one("a, h3, h4, .opening-title")
        title = _text_from_node(title_node)
        if not title:
            continue

        link = card.select_one("a[href]")
        job_url = _absolute_url(str(link["href"]) if link and link.get("href") else "", base_url)

        location = _text_from_node(
            card.select_one(".location, .opening-location, [class*='location']")
        )
        department = _text_from_node(
            card.select_one(".department, .opening-department, [class*='department']")
        )
        description = _description_from_card(card)

        job_id = str(
            card.get("data-id")
            or card.get("data-mapped-job-id")
            or card.get("id")
            or ""
        ) or _job_id_from_url(job_url, title)

        postings.append(
            JobPosting(
                id=job_id,
                title=title,
                department=department,
                location=location,
                url=job_url,
                description=description,
                company_name=company_name,
            )
        )
    return postings


def _parse_generic_job_cards(
    soup: BeautifulSoup,
    company_name: str,
    base_url: str,
) -> list[JobPosting]:
    """Heuristic fallback for unknown HTML job boards."""
    postings: list[JobPosting] = []
    seen_titles: set[str] = set()

    selectors = (
        "article",
        "[class*='job-listing']",
        "[class*='job-card']",
        "[class*='job-result']",
        "[class*='posting']",
        "[class*='opening']",
        "li[class*='job']",
    )
    cards: list[Tag] = []
    for selector in selectors:
        cards.extend(soup.select(selector))

    for card in cards:
        title_node = card.select_one("h2 a, h3 a, h2, h3, .job-title, [class*='title']")
        title = _text_from_node(title_node)
        if not title or title.lower() in seen_titles:
            continue
        if len(title) < 4:
            continue

        link = card.select_one("a[href]")
        job_url = _absolute_url(str(link["href"]) if link and link.get("href") else "", base_url)
        location = _text_from_node(
            card.select_one(".location, [class*='location'], .meta, [class*='meta']")
        )
        department = _text_from_node(
            card.select_one(".department, [class*='department'], .team, [class*='team']")
        )
        description = _description_from_card(card)

        seen_titles.add(title.lower())
        postings.append(
            JobPosting(
                id=_job_id_from_url(job_url, title),
                title=title,
                department=department,
                location=location,
                url=job_url,
                description=description,
                company_name=company_name,
            )
        )
    return postings


def parse_html_jobs(
    html: str,
    url: str,
    company_name: str,
) -> list[JobPosting]:
    """Extract structured job postings from an HTML careers page when possible."""
    soup = BeautifulSoup(html, "lxml")
    base_url = url

    for parser in (_parse_lever_postings, _parse_greenhouse_openings, _parse_generic_job_cards):
        postings = parser(soup, company_name, base_url)
        if postings:
            return postings

    return []


def strip_html_description(raw_html: str) -> str:
    """Normalize HTML job description snippets to plain searchable text."""
    if not raw_html:
        return ""
    if "<" in raw_html and ">" in raw_html:
        return _strip_html(raw_html)
    return _normalize_whitespace(_HTML_TAG_RE.sub(" ", raw_html))
