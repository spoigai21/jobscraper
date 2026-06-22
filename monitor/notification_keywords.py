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
        "computer vision",
        "perception",
        "cv",
        "autonomy",
        "av",
        "robotics software",
        "simulation",
        "mapping",
        "localization",
    }
)

_LEVEL_TERMS: tuple[str, ...] = (
    "undergrad",
    "undergraduate",
    "bachelor",
    "bs student",
    "intern",
    "internship",
    "co-op",
    "residency",
)

_TIMEFRAME_TERMS: tuple[str, ...] = (
    "spring 2027",
    "summer 2027",
    "fall 2027",
    "co-op 2027",
    "winter 2027",
    "2027",
    "2028",
)

_TECH_DISPLAY: dict[str, str] = {
    "python": "Python",
    "pytorch": "PyTorch",
    "opencv": "OpenCV",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "react": "React",
    "docker": "Docker",
    "redis": "Redis",
    "postgresql": "PostgreSQL",
    "aws": "AWS",
    "gcp": "GCP",
    "xgboost": "XGBoost",
    "scikit-learn": "scikit-learn",
    "rag": "RAG",
    "llm": "LLM",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "sql": "SQL",
    "pandas": "pandas",
    "numpy": "NumPy",
    "streamlit": "Streamlit",
    "gradio": "Gradio",
    "onnx": "ONNX",
    "firestore": "Firestore",
    "ci/cd": "CI/CD",
    "lightgbm": "LightGBM",
    "mediapipe": "MediaPipe",
    "yolo": "YOLO",
    "rest": "REST",
}

_MAX_TOTAL = 5
_MAX_LEVEL = 2
_MAX_TIMEFRAME = 2
_MAX_TECH = 2


def _contains_term(text: str, term: str) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return False
    if " " in normalized:
        return normalized in text
    return re.search(rf"\b{re.escape(normalized)}\b", text) is not None


def _display_keyword(term: str) -> str:
    lowered = term.strip().lower()
    if lowered in _TECH_DISPLAY:
        return _TECH_DISPLAY[lowered]
    if lowered in {t.lower() for t in _LEVEL_TERMS + _TIMEFRAME_TERMS}:
        return lowered
    if lowered in _GENERIC_ROLE_TERMS:
        return term
    if term.islower() and term.replace("-", "").replace("/", "").isalpha():
        return term.capitalize()
    return term


def _find_matches(text: str, terms: tuple[str, ...] | list[str]) -> list[str]:
    """Return profile-order matches found in text (deduped, display-cased)."""
    lowered = text.lower()
    seen: set[str] = set()
    matches: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen or key in _GENERIC_ROLE_TERMS:
            continue
        if _contains_term(lowered, term):
            seen.add(key)
            matches.append(_display_keyword(term))
    return matches


def _level_terms(profile: UserProfile | None) -> tuple[str, ...]:
    terms = list(_LEVEL_TERMS)
    if profile is not None:
        for term in profile.cycle_keywords:
            key = term.lower()
            if key in {"intern", "internship", "co-op", "residency"} and term not in terms:
                terms.append(term)
    return tuple(terms)


def _timeframe_terms(profile: UserProfile | None) -> tuple[str, ...]:
    terms = list(_TIMEFRAME_TERMS)
    if profile is not None:
        for term in profile.cycle_keywords:
            key = term.lower()
            if key in {t.lower() for t in _LEVEL_TERMS}:
                continue
            if term not in terms:
                terms.append(term)
    return tuple(terms)


def _tech_terms(profile: UserProfile | None) -> tuple[str, ...]:
    if profile is None:
        return ()
    return profile.skills_strong + profile.skills_bonus


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
    """Pick 4-5 diverse keywords across level, timeframe, and tech categories."""
    searchable = text.lower()
    if not searchable.strip():
        searchable = trigger_keyword.lower()

    level_hits = _find_matches(searchable, _level_terms(profile))
    timeframe_hits = _find_matches(searchable, _timeframe_terms(profile))
    tech_hits = _find_matches(searchable, _tech_terms(profile))

    selected: list[str] = []
    used: set[str] = set()

    def _pick(source: list[str], max_count: int) -> None:
        count = 0
        for term in source:
            if count >= max_count or len(selected) >= limit:
                break
            key = term.lower()
            if key in used:
                continue
            selected.append(term)
            used.add(key)
            count += 1

    _pick(level_hits, _MAX_LEVEL)
    _pick(timeframe_hits, _MAX_TIMEFRAME)
    _pick(tech_hits, _MAX_TECH)

    trigger = _display_keyword(trigger_keyword.strip())
    trigger_key = trigger.lower()
    if (
        trigger
        and trigger_key not in used
        and trigger_key not in _GENERIC_ROLE_TERMS
        and len(selected) < limit
    ):
        selected.append(trigger)
        used.add(trigger_key)

    return tuple(selected[:limit])
