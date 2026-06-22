"""Tests for diverse push notification keyword selection."""

from __future__ import annotations

from monitor.notification_keywords import select_notification_keywords, title_from_diff_snippet
from monitor.profile import load_profile


class TestSelectNotificationKeywords:
    def test_picks_cycle_level_and_tech_terms(self) -> None:
        profile = load_profile()
        text = (
            "Software Engineering Intern - Summer 2027 undergraduate role. "
            "Requirements: Python, FastAPI, computer vision."
        )
        selected = select_notification_keywords(
            text,
            profile=profile,
            trigger_keyword="intern",
        )

        lowered = {term.lower() for term in selected}
        assert "summer 2027" in lowered
        assert "python" in lowered or "fastapi" in lowered
        assert len(selected) <= 5

    def test_falls_back_to_trigger_when_text_empty(self) -> None:
        selected = select_notification_keywords(
            "",
            profile=load_profile(),
            trigger_keyword="internship",
        )
        assert selected == ("internship",)


class TestTitleFromDiffSnippet:
    def test_extracts_title_before_metadata(self) -> None:
        assert (
            title_from_diff_snippet("New: Perception Intern (Autonomy, SF)")
            == "Perception Intern"
        )
