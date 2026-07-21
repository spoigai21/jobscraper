"""Tests for profile.yaml loading and alert channel routing."""

from __future__ import annotations

from pathlib import Path

import pytest

from monitor.profile import DEFAULT_PROFILE_PATH, load_profile


class TestLoadProfile:
    def test_default_profile_path_exists(self) -> None:
        assert DEFAULT_PROFILE_PATH.is_file()

    def test_loads_user_info(self, profile) -> None:
        assert profile.user.name == "Savir Khanna"
        assert profile.user.school == "Northeastern University"
        assert profile.user.degree == "BS Data Science & Physics"
        assert profile.user.grad_year == 2028
        assert profile.user.graduation == "June 2028"

    def test_target_cycle_year_is_2027(self, profile) -> None:
        assert profile.target_cycle_year == 2027

    def test_cycle_keywords_include_2027_seasons(self, profile) -> None:
        keywords = {kw.lower() for kw in profile.cycle_keywords}
        assert "spring 2027" in keywords
        assert "summer 2027" in keywords
        assert "fall 2027" in keywords
        assert "co-op 2027" in keywords
        assert "intern" in keywords
        assert "residency" in keywords

    def test_location_config(self, profile) -> None:
        assert profile.location.remote_ok is True
        assert "US" in profile.location.countries

    def test_roles_and_skills_loaded(self, profile) -> None:
        roles = {role.lower() for role in profile.roles_include}
        assert "perception" in roles
        assert "computer vision" in roles
        assert "software engineer" in roles

        skills = {skill.lower() for skill in profile.skills_strong}
        assert "pytorch" in skills
        assert "fastapi" in skills
        assert "yolo" in skills
        assert "rag" in skills

    def test_exclusion_lists(self, profile) -> None:
        assert "marketing" in profile.roles_exclude
        assert "firmware" in profile.roles_exclude
        assert "phd" in profile.level_exclude

    def test_prestige_tiers(self, profile) -> None:
        assert profile.prestige.tier_for_company("Google") == "s"
        assert profile.prestige.tier_for_company("SpaceX") == "a"
        assert profile.prestige.tier_for_company("Airbnb") == "a"
        assert profile.prestige.tier_for_company("Skydio") == "b"
        assert profile.prestige.tier_for_company("Bloomberg") == "b"
        assert profile.prestige.tier_for_company("Wing") == "b"
        assert profile.prestige.tier_for_company("JPL") == "b"
        assert profile.prestige.tier_for_company("Unknown Corp") is None

    def test_scoring_weights(self, profile) -> None:
        assert profile.scoring.title_dream_role == 4
        assert profile.scoring.prestige_tier_s == 4
        assert profile.scoring.space_perception_bonus == 2

    def test_alert_tier_channels(self, profile) -> None:
        # Channels are a personal preference and change freely in profile.yaml;
        # assert the invariants instead of the current selection.
        valid = {"push", "call", "sms", "email"}
        assert set(profile.alerts.standard.channels) <= valid
        assert set(profile.alerts.high.channels) <= valid
        assert profile.alerts.standard.channels, "standard tier needs a channel"
        # Escalating to high tier must never notify on fewer channels.
        assert set(profile.alerts.high.channels) >= set(
            profile.alerts.standard.channels
        )
        assert profile.alerts.high_score_threshold == 7

    def test_alert_channels_for_score(self, profile) -> None:
        threshold = profile.alerts.high_score_threshold
        assert profile.alert_channels_for_score(threshold - 1) == (
            profile.alerts.standard.channels
        )
        assert profile.alert_channels_for_score(threshold) == profile.alerts.high.channels
        assert profile.alert_channels_for_score(threshold + 5) == (
            profile.alerts.high.channels
        )

    def test_load_profile_from_explicit_path(self) -> None:
        loaded = load_profile(DEFAULT_PROFILE_PATH)
        assert loaded.target_cycle_year == 2027

    def test_missing_profile_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.yaml"
        with pytest.raises(FileNotFoundError, match="Profile file not found"):
            load_profile(missing)
