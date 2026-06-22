"""Select diverse notification keywords from job text for push alerts."""

from __future__ import annotations

import re

from monitor.profile import UserProfile

_GENERIC_ROLE_TERMS: frozenset[str] = frozenset(
    {
        "software engineer",
        "software engineering",
        "software development",
        "swe",
        "sde",
        "software",
        "infra",
        "infrastructure",
        "data science",
        "data scientist",
        "data engineer",
        "ml",
        "machine learning",
        "ml engineer",
        "ai engineer",
        "platform",
        "backend",
        "frontend",
        "full stack",
        "fullstack",
        "devops",
        "sre",
        "site reliability",
        "cloud",
        "distributed systems",
        "analytics engineer",
        "applied scientist",
        "research engineer",
    }
)

_EXTRA_LEVEL_TERMS: tuple[str, ...] = (
    "undergrad",
    "undergraduate",
    "bachelor",
    "bs student",
)

_MAX_TOTAL = 5
_MAX_CYCLE = 2
_MAX_TECH = 2
_MAX_DOMAIN = 1


def _contains_term(text: str, term: str) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return False
    if " " in normalized:
        return normalized in text
    return re.search(rf"\b{re.escape(normalized)}\b", text) is not None


def _find_matches(text: str, terms: tuple[str, ...] | list[str]) -> list[str]:
    """Return profile-order matches found in text (deduped, case preserved)."""
    lowered = text.lower()
    seen: set[str] = set()
    matches: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        if _contains_term(lowered, term):
            seen.add(key)
            matches.append(term)
    return matches


def _cycle_terms(profile: UserProfile | None) -> tuple[str, ...]:
    if profile is None:
        return _EXTRA_LEVEL_TERMS
    return profile.cycle_keywords + _EXTRA_LEVEL_TERMS


def _tech_terms(profile: UserProfile | None) -> tuple[str, ...]:
    if profile is None:
        return ()
    return profile.skills_strong + profile.skills_bonus


def _domain_terms(profile: UserProfile | None) -> tuple[str, ...]:
    if profile is None:
        return ()
    return tuple(
        term
        for term in profile.roles_include
        if term.lower() not in _GENERIC_ROLE_TERMS
    )


def title_from_diff_snippet(diff_snippet: str) -> str:
    """Extract a job title from an HTML diff snippet like ``New: Title (meta)``."""
    if not diff_snippet.startswith("New: "):
        return ""
    rest = diff_snippet[5:].strip()
    if " (" in rest:
        return rest.split(" (", 1)[0].strip()
    return rest.strip()


def select_notification_keywords(
    text: str,
    *,
    profile: UserProfile | None,
    trigger_keyword: str,
    limit: int = _MAX_TOTAL,
) -> tuple[str, ...]:
    """Pick 4-5 diverse keywords: cycle/level, tech, and at most one domain term."""
    searchable = text.lower()
    if not searchable.strip():
        searchable = trigger_keyword.lower()

    cycle_hits = _find_matches(searchable, _cycle_terms(profile))
    tech_hits = _find_matches(searchable, _tech_terms(profile))
    domain_hits = _find_matches(searchable, _domain_terms(profile))

    selected: list[str] = []
    used: set[str] = set()

    def _pick(source: list[str], max_count: int) -> None:
        count = 0
        for term in source:
            if count >= max_count:
                break
            key = term.lower()
            if key in used:
                continue
            selected.append(term)
            used.add(key)
            count += 1

    _pick(cycle_hits, _MAX_CYCLE)
    _pick(tech_hits, _MAX_TECH)
    _pick(domain_hits, _MAX_DOMAIN)

    trigger = trigger_keyword.strip()
    if trigger and trigger.lower() not in used and len(selected) < limit:
        selected.append(trigger)
        used.add(trigger.lower())

    return tuple(selected[:limit])
