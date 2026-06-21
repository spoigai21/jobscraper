"""Load user profile filters, skills, prestige tiers, and alert thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

AlertChannel = Literal["push", "call", "sms", "email"]
PrestigeTier = Literal["s", "a", "b", "c"]

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent / "profile.yaml"
_PRESTIGE_TIER_KEYS = ("tier_s", "tier_a", "tier_b", "tier_c")
_PRESTIGE_TIER_LABELS: dict[str, PrestigeTier] = {
    "tier_s": "s",
    "tier_a": "a",
    "tier_b": "b",
    "tier_c": "c",
}


@dataclass(frozen=True, slots=True)
class UserInfo:
    name: str
    school: str
    degree: str
    grad_year: int
    graduation: str


@dataclass(frozen=True, slots=True)
class LocationConfig:
    countries: list[str]
    remote_ok: bool


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    title_dream_role: int
    title_swe_role: int
    title_data_role: int
    department_engineering: int
    skill_strong_match: int
    skill_strong_cap: int
    skill_bonus_match: int
    skill_bonus_cap: int
    prestige_tier_s: int
    prestige_tier_a: int
    prestige_tier_b: int
    prestige_tier_c: int
    space_perception_bonus: int


@dataclass(frozen=True, slots=True)
class AlertTierConfig:
    channels: tuple[AlertChannel, ...]


@dataclass(frozen=True, slots=True)
class AlertConfig:
    standard: AlertTierConfig
    high: AlertTierConfig
    high_score_threshold: int


@dataclass(frozen=True, slots=True)
class PrestigeTiers:
    tier_s: tuple[str, ...]
    tier_a: tuple[str, ...]
    tier_b: tuple[str, ...]
    tier_c: tuple[str, ...]

    def tier_for_company(self, company: str) -> PrestigeTier | None:
        normalized = company.strip().lower()
        for tier_key in _PRESTIGE_TIER_KEYS:
            companies = getattr(self, tier_key)
            if any(name.lower() == normalized for name in companies):
                return _PRESTIGE_TIER_LABELS[tier_key]
        return None

    def prestige_bonus(self, company: str, weights: ScoringWeights) -> int:
        tier = self.tier_for_company(company)
        if tier == "s":
            return weights.prestige_tier_s
        if tier == "a":
            return weights.prestige_tier_a
        if tier == "b":
            return weights.prestige_tier_b
        if tier == "c":
            return weights.prestige_tier_c
        return 0


@dataclass(frozen=True, slots=True)
class UserProfile:
    user: UserInfo
    target_cycle_year: int
    cycle_keywords: tuple[str, ...]
    location: LocationConfig
    roles_include: tuple[str, ...]
    roles_exclude: tuple[str, ...]
    level_exclude: tuple[str, ...]
    skills_strong: tuple[str, ...]
    skills_bonus: tuple[str, ...]
    prestige: PrestigeTiers
    scoring: ScoringWeights
    alerts: AlertConfig

    def alert_channels_for_score(self, score: int) -> tuple[AlertChannel, ...]:
        if score >= self.alerts.high_score_threshold:
            return self.alerts.high.channels
        return self.alerts.standard.channels


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"profile.yaml: expected mapping at '{key}'")
    return value


def _require_str_list(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"profile.yaml: expected list[str] at '{key}'")
    return tuple(value)


def _parse_alert_channels(channels: list[str], context: str) -> tuple[AlertChannel, ...]:
    allowed: set[AlertChannel] = {"push", "call", "sms", "email"}
    parsed: list[AlertChannel] = []
    for channel in channels:
        if channel not in allowed:
            raise ValueError(
                f"profile.yaml: invalid alert channel '{channel}' in {context}; "
                f"expected one of {sorted(allowed)}"
            )
        parsed.append(channel)
    if not parsed:
        raise ValueError(f"profile.yaml: {context} must include at least one channel")
    return tuple(parsed)


def _parse_user(data: dict[str, Any]) -> UserInfo:
    user = _require_mapping(data, "user")
    grad_year = user.get("grad_year")
    if not isinstance(grad_year, int):
        raise ValueError("profile.yaml: user.grad_year must be an integer")
    return UserInfo(
        name=str(user.get("name", "")),
        school=str(user.get("school", "")),
        degree=str(user.get("degree", "")),
        grad_year=grad_year,
        graduation=str(user.get("graduation", "")),
    )


def _parse_location(data: dict[str, Any]) -> LocationConfig:
    location = _require_mapping(data, "location")
    remote_ok = location.get("remote_ok")
    if not isinstance(remote_ok, bool):
        raise ValueError("profile.yaml: location.remote_ok must be a boolean")
    return LocationConfig(
        countries=list(_require_str_list(location, "countries")),
        remote_ok=remote_ok,
    )


def _parse_scoring(data: dict[str, Any]) -> ScoringWeights:
    scoring = _require_mapping(data, "scoring")
    fields = (
        "title_dream_role",
        "title_swe_role",
        "title_data_role",
        "department_engineering",
        "skill_strong_match",
        "skill_strong_cap",
        "skill_bonus_match",
        "skill_bonus_cap",
        "prestige_tier_s",
        "prestige_tier_a",
        "prestige_tier_b",
        "prestige_tier_c",
        "space_perception_bonus",
    )
    values: dict[str, int] = {}
    for field in fields:
        value = scoring.get(field)
        if not isinstance(value, int):
            raise ValueError(f"profile.yaml: scoring.{field} must be an integer")
        values[field] = value
    return ScoringWeights(**values)


def _parse_prestige(data: dict[str, Any]) -> PrestigeTiers:
    prestige = _require_mapping(data, "prestige")
    return PrestigeTiers(
        tier_s=_require_str_list(prestige, "tier_s"),
        tier_a=_require_str_list(prestige, "tier_a"),
        tier_b=_require_str_list(prestige, "tier_b"),
        tier_c=_require_str_list(prestige, "tier_c"),
    )


def _parse_alerts(data: dict[str, Any]) -> AlertConfig:
    alerts = _require_mapping(data, "alerts")
    standard = _require_mapping(alerts, "standard")
    high = _require_mapping(alerts, "high")

    standard_channels = standard.get("channels")
    high_channels = high.get("channels")
    threshold = high.get("score_threshold")

    if not isinstance(standard_channels, list):
        raise ValueError("profile.yaml: alerts.standard.channels must be a list")
    if not isinstance(high_channels, list):
        raise ValueError("profile.yaml: alerts.high.channels must be a list")
    if not isinstance(threshold, int):
        raise ValueError("profile.yaml: alerts.high.score_threshold must be an integer")

    return AlertConfig(
        standard=AlertTierConfig(
            channels=_parse_alert_channels(standard_channels, "alerts.standard.channels"),
        ),
        high=AlertTierConfig(
            channels=_parse_alert_channels(high_channels, "alerts.high.channels"),
        ),
        high_score_threshold=threshold,
    )


def load_profile(path: Path | str | None = None) -> UserProfile:
    """Load and validate the user profile from ``profile.yaml``."""
    profile_path = Path(path) if path is not None else DEFAULT_PROFILE_PATH
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile file not found: {profile_path}")

    with profile_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ValueError(f"Profile file must contain a mapping: {profile_path}")

    target_cycle_year = raw.get("target_cycle_year")
    if not isinstance(target_cycle_year, int):
        raise ValueError("profile.yaml: target_cycle_year must be an integer")

    return UserProfile(
        user=_parse_user(raw),
        target_cycle_year=target_cycle_year,
        cycle_keywords=_require_str_list(raw, "cycle_keywords"),
        location=_parse_location(raw),
        roles_include=_require_str_list(raw, "roles_include"),
        roles_exclude=_require_str_list(raw, "roles_exclude"),
        level_exclude=_require_str_list(raw, "level_exclude"),
        skills_strong=_require_str_list(raw, "skills_strong"),
        skills_bonus=_require_str_list(raw, "skills_bonus"),
        prestige=_parse_prestige(raw),
        scoring=_parse_scoring(raw),
        alerts=_parse_alerts(raw),
    )
