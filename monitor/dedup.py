"""Content-level dedup keys for alerts.

Job IDs are only stable while a posting stays up. Companies routinely close a
requisition and re-post the identical role under a fresh ID (Copart cycles
"Software Engineer Intern" through new Workday req numbers every couple of
weeks), and aggregator feeds mint a new UUID for each of those. ID diffing
alone therefore re-alerts on the same job indefinitely.

A dedup key normalizes employer + role title so those re-posts collapse onto
one key, which the store remembers across polls (see
``StateStore.recent_dedup_keys``).
"""

from __future__ import annotations

import re

# Cosmetic separators used to fold an employer into a title, e.g.
# "Copart — Software Engineer Intern" (the Simplify aggregator does this).
_TITLE_SEPARATORS = ("—", "–", "-", "|", ":")

# Terms that vary between re-posts of the same role without changing the job.
_NOISE_TOKENS = frozenset(
    {
        "summer",
        "fall",
        "autumn",
        "winter",
        "spring",
        "the",
        "a",
        "an",
        "and",
        "of",
        "for",
        "at",
        "in",
        "us",
        "usa",
        "united",
        "states",
    }
)

# Spelling variants that name the same role.
_SYNONYMS = {
    "engineering": "engineer",
    "engineers": "engineer",
    "internship": "intern",
    "internships": "intern",
    "interns": "intern",
    "developers": "developer",
    "swe": "software engineer",
}

_YEAR = re.compile(r"^(19|20)\d{2}$")
_NON_ALNUM = re.compile(r"[^a-z0-9+#]+")
# "Co-op", "co op" and "coop" all name the same thing; fold before tokenizing
# so the hyphen doesn't split it into two meaningless tokens.
_COOP = re.compile(r"\bco[\s\-_]?op\b")


def _normalize(text: str) -> str:
    tokens: list[str] = []
    folded = _COOP.sub("coop", text.lower())
    for raw in _NON_ALNUM.sub(" ", folded).split():
        if _YEAR.match(raw) or raw in _NOISE_TOKENS:
            continue
        token = _SYNONYMS.get(raw, raw)
        if token and (not tokens or tokens[-1] != token):
            tokens.extend(token.split())
    return " ".join(tokens)


def _strip_company_prefix(title: str, company: str) -> str:
    """Drop a leading "<Company> — " prefix so it isn't counted twice."""
    stripped = title.strip()
    if company and stripped.lower().startswith(company.strip().lower()):
        remainder = stripped[len(company.strip()) :].lstrip()
        # Only treat it as a prefix if a separator followed the company name;
        # otherwise "Apple Systems Engineer Intern" would lose "Apple".
        if remainder[:1] in _TITLE_SEPARATORS:
            return remainder[1:].strip()
    return stripped


def job_dedup_key(company: str, title: str) -> str:
    """Stable key identifying "the same role at the same employer".

    Returns an empty string when there is nothing to key on, which callers
    treat as "not dedupable" (never suppressed).
    """
    role = _normalize(_strip_company_prefix(title, company))
    employer = _normalize(company)
    if not role:
        return ""
    return f"{employer}::{role}"
