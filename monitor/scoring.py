"""Relevance scoring and tier classification for parsed job postings."""

from __future__ import annotations

import re

from monitor.models import AlertTier, JobPosting
from monitor.profile import UserProfile

_DREAM_ROLE_KEYWORDS: tuple[str, ...] = (
    "perception",
    "computer vision",
    "cv",
    "autonomy",
    "av",
    "robotics software",
    "simulation",
    "mapping",
    "localization",
)

_SWE_ROLE_KEYWORDS: tuple[str, ...] = (
    "software engineer",
    "software engineering",
    "swe",
    "sde",
    "software development",
    "platform",
    "infrastructure",
    "infra",
    "devops",
    "sre",
    "site reliability",
    "backend",
    "frontend",
    "full stack",
    "fullstack",
    "cloud",
    "distributed systems",
    "machine learning engineer",
    "ml engineer",
)

_DATA_ROLE_KEYWORDS: tuple[str, ...] = (
    "data science",
    "data scientist",
    "data engineer",
    "analytics engineer",
    "applied scientist",
    "research engineer",
)

_ENGINEERING_DEPARTMENTS: tuple[str, ...] = (
    "engineering",
    "software",
    "ai",
    "ml",
    "autonomy",
    "perception",
    "research",
    "platform",
    "infrastructure",
    "machine learning",
)

_US_STATE_ABBREVS: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    }
)

_US_STATE_NAMES: frozenset[str] = frozenset(
    {
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "district of columbia",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
    }
)

_SPACE_PERCEPTION_KEYWORDS: tuple[str, ...] = (
    "perception",
    "computer vision",
    "autonomy",
    "robotics",
    "simulation",
    "mapping",
    "localization",
    "aerospace",
    "av",
)


def _contains_term(text: str, term: str) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return False
    if " " in normalized:
        return normalized in text
    return re.search(rf"\b{re.escape(normalized)}\b", text) is not None


def _searchable_text(job: JobPosting) -> str:
    parts = (job.title, job.department, job.description, job.location)
    return " ".join(part for part in parts if part).lower()


def _title_text(job: JobPosting) -> str:
    return job.title.lower()


def _department_text(job: JobPosting) -> str:
    return job.department.lower()


def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(_contains_term(text, keyword) for keyword in keywords)


def _location_matches_profile(location: str, profile: UserProfile) -> bool:
    """Return True when a posting location fits the profile's geography."""
    normalized = location.strip()
    if not normalized:
        return True

    lowered = normalized.lower()
    if profile.location.remote_ok and "remote" in lowered:
        return True

    for country in profile.location.countries:
        if _contains_term(lowered, country):
            return True

    if re.search(
        r",\s*(" + "|".join(sorted(_US_STATE_ABBREVS)) + r")\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        return True

    if " - " in normalized:
        state_part = normalized.split(" - ", 1)[0].strip().lower()
        if state_part in _US_STATE_NAMES:
            return True

    return False


def should_exclude(job: JobPosting, profile: UserProfile) -> bool:
    """Return True when a posting should be dropped before alerting."""
    text = _searchable_text(job)

    for term in profile.roles_exclude:
        if _contains_term(text, term):
            return True

    for term in profile.level_exclude:
        if _contains_term(text, term):
            return True

    if not _location_matches_profile(job.location, profile):
        return True

    return False


def score_job(job: JobPosting, profile: UserProfile) -> int:
    """Score a job posting for relevance using role, skill, and prestige signals."""
    weights = profile.scoring
    title = _title_text(job)
    department = _department_text(job)
    description = job.description.lower()
    score = 0

    if _matches_any(title, _DREAM_ROLE_KEYWORDS):
        score += weights.title_dream_role
    elif _matches_any(title, _SWE_ROLE_KEYWORDS):
        score += weights.title_swe_role
    elif _matches_any(title, _DATA_ROLE_KEYWORDS):
        score += weights.title_data_role

    if _matches_any(department, _ENGINEERING_DEPARTMENTS):
        score += weights.department_engineering

    strong_hits = sum(
        1 for skill in profile.skills_strong if _contains_term(description, skill)
    )
    score += min(strong_hits * weights.skill_strong_match, weights.skill_strong_cap)

    bonus_hits = sum(
        1 for skill in profile.skills_bonus if _contains_term(description, skill)
    )
    score += min(bonus_hits * weights.skill_bonus_match, weights.skill_bonus_cap)

    score += profile.prestige.prestige_bonus(job.company_name, weights)

    space_text = f"{title} {department}"
    if _matches_any(space_text, _SPACE_PERCEPTION_KEYWORDS):
        score += weights.space_perception_bonus

    return score


def classify_tier(score: int, profile: UserProfile) -> AlertTier:
    """Map a relevance score to an alert tier."""
    if score >= profile.alerts.high_score_threshold:
        return "high"
    return "standard"
