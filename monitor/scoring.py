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

# Named explicitly in job locations; omit ambiguous tokens (e.g. "georgia" = US state).
_EXPLICIT_NON_US_COUNTRY_TERMS: frozenset[str] = frozenset(
    {
        "afghanistan",
        "albania",
        "algeria",
        "argentina",
        "armenia",
        "australia",
        "austria",
        "azerbaijan",
        "bahrain",
        "bangladesh",
        "belarus",
        "belgium",
        "bolivia",
        "bosnia",
        "botswana",
        "brazil",
        "bulgaria",
        "cambodia",
        "cameroon",
        "canada",
        "chile",
        "china",
        "colombia",
        "costa rica",
        "croatia",
        "cyprus",
        "czech republic",
        "czechia",
        "denmark",
        "dominican republic",
        "ecuador",
        "egypt",
        "el salvador",
        "estonia",
        "ethiopia",
        "finland",
        "france",
        "germany",
        "ghana",
        "greece",
        "guatemala",
        "hong kong",
        "hungary",
        "iceland",
        "india",
        "indonesia",
        "iran",
        "iraq",
        "ireland",
        "israel",
        "italy",
        "jamaica",
        "japan",
        "jordan",
        "kazakhstan",
        "kenya",
        "kuwait",
        "latvia",
        "lebanon",
        "lithuania",
        "luxembourg",
        "malaysia",
        "malta",
        "mexico",
        "mongolia",
        "morocco",
        "myanmar",
        "nepal",
        "netherlands",
        "new zealand",
        "nigeria",
        "north macedonia",
        "norway",
        "oman",
        "pakistan",
        "panama",
        "paraguay",
        "peru",
        "philippines",
        "poland",
        "portugal",
        "qatar",
        "romania",
        "russia",
        "saudi arabia",
        "serbia",
        "singapore",
        "slovakia",
        "slovenia",
        "south africa",
        "south korea",
        "spain",
        "sri lanka",
        "sweden",
        "switzerland",
        "taiwan",
        "thailand",
        "tunisia",
        "turkey",
        "ukraine",
        "united arab emirates",
        "united kingdom",
        "uruguay",
        "uzbekistan",
        "venezuela",
        "vietnam",
        "england",
        "scotland",
        "wales",
        "northern ireland",
        "uk",
        "u.k.",
        "uae",
        "prc",
        "people's republic of china",
        "republic of korea",
        "republic of ireland",
        "puerto rico",
        "guam",
        "american samoa",
        "northern mariana islands",
        "u.s. virgin islands",
        "us virgin islands",
    }
)

_CANADIAN_PROVINCE_ABBREVS: frozenset[str] = frozenset(
    {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
)

_CANADIAN_PROVINCE_NAMES: frozenset[str] = frozenset(
    {
        "alberta",
        "british columbia",
        "manitoba",
        "new brunswick",
        "newfoundland and labrador",
        "nova scotia",
        "nunavut",
        "ontario",
        "prince edward island",
        "quebec",
        "saskatchewan",
        "northwest territories",
        "yukon",
    }
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


def _has_us_location_signal(location: str, profile: UserProfile) -> bool:
    """Return True when a location string references the 50 US states or DC."""
    lowered = location.lower()
    for country in profile.location.countries:
        if _contains_term(lowered, country):
            return True
    if _contains_term(lowered, "u.s.") or _contains_term(lowered, "u.s.a."):
        return True
    if _contains_term(lowered, "united states of america"):
        return True

    if re.search(
        r",\s*(" + "|".join(sorted(_US_STATE_ABBREVS)) + r")\b",
        location,
        flags=re.IGNORECASE,
    ):
        return True

    if " - " in location:
        state_part = location.split(" - ", 1)[0].strip().lower()
        if state_part in _US_STATE_NAMES:
            return True

    return False


def _has_canadian_location_signal(location: str) -> bool:
    """Return True when a location string references Canada or a province."""
    lowered = location.lower()
    if _contains_term(lowered, "canada"):
        return True

    if re.search(
        r",\s*(" + "|".join(sorted(_CANADIAN_PROVINCE_ABBREVS)) + r")\b",
        location,
        flags=re.IGNORECASE,
    ):
        return True

    if " - " in location:
        province_part = location.split(" - ", 1)[0].strip().lower()
        if province_part in _CANADIAN_PROVINCE_NAMES:
            return True

    return any(
        _contains_term(lowered, province) for province in _CANADIAN_PROVINCE_NAMES
    )


def _has_explicit_non_us_country(location: str) -> bool:
    """Return True when a location string names a non-US country or Canada."""
    if _has_canadian_location_signal(location):
        return True

    lowered = location.lower()
    return any(
        _contains_term(lowered, country) for country in _EXPLICIT_NON_US_COUNTRY_TERMS
    )


def _location_matches_profile(location: str, profile: UserProfile) -> bool:
    """Return True when a posting location should not be excluded for geography.

    Exclude only when a non-US country is named and there is no US signal.
    Vague locations (e.g. "3 Locations", city-only strings) are allowed.
    Mixed US + international locations are allowed. US coverage is the 50 states
    and DC only — territories such as Puerto Rico are treated as non-US.
    Canadian provinces (e.g. "Toronto, ON") count as non-US even without
    "Canada" in the string. Foreign-only remote locations are excluded.
    """
    normalized = location.strip()
    if not normalized:
        return True

    lowered = normalized.lower()
    if profile.location.remote_ok and "remote" in lowered:
        if _has_explicit_non_us_country(normalized) and not _has_us_location_signal(
            normalized, profile
        ):
            return False
        return True

    if _has_us_location_signal(normalized, profile):
        return True

    if _has_explicit_non_us_country(normalized):
        return False

    return True


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
