"""Tests for job relevance scoring, tier classification, and exclusions."""

from __future__ import annotations

import pytest

from monitor.models import JobPosting
from monitor.scoring import classify_tier, score_job, should_exclude


def _job(
    *,
    title: str,
    department: str = "Engineering",
    description: str = "",
    company_name: str = "ExampleCo",
    job_id: str = "test-1",
    location: str = "Remote, US",
) -> JobPosting:
    return JobPosting(
        id=job_id,
        title=title,
        department=department,
        location=location,
        url=f"https://example.com/jobs/{job_id}",
        description=description,
        company_name=company_name,
    )


class TestAerialAirportStyleScoring:
    """CV / perception / YOLO roles like the Aerial Airport resume project."""

    def test_perception_cv_intern_scores_high(self, profile) -> None:
        job = _job(
            title="Computer Vision Intern — Perception",
            department="Perception Engineering",
            company_name="Skydio",
            description=(
                "Build YOLOv8 object detectors with PyTorch and OpenCV for "
                "aerospace perception stacks. Deploy models on edge hardware."
            ),
        )

        score = score_job(job, profile)

        assert score >= profile.alerts.high_score_threshold
        assert classify_tier(score, profile) == "high"
        assert not should_exclude(job, profile)

    def test_yolo_skills_contribute_to_score(self, profile) -> None:
        with_yolo = _job(
            title="Perception Intern",
            department="Autonomy",
            company_name="Waymo",
            description="Experience with YOLO, PyTorch, and OpenCV required.",
        )
        without_skills = _job(
            title="Perception Intern",
            department="Autonomy",
            company_name="Waymo",
            description="General software internship on the autonomy team.",
            job_id="test-2",
        )

        assert score_job(with_yolo, profile) > score_job(without_skills, profile)


class TestVALTStyleScoring:
    """FastAPI / microservices / RAG platform roles like the VALT project."""

    def test_fastapi_microservices_rag_scores_high(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Platform Engineering",
            company_name="Ramp",
            description=(
                "Build FastAPI microservices on GCP. Design RAG pipelines with "
                "LLM integrations, Redis caching, and Docker deployments for our "
                "health platform."
            ),
        )

        score = score_job(job, profile)

        assert score >= profile.alerts.high_score_threshold
        assert classify_tier(score, profile) == "high"

    def test_backend_platform_without_dream_title_is_standard_or_high(
        self, profile
    ) -> None:
        job = _job(
            title="Backend Platform Intern",
            department="Infrastructure",
            description="REST APIs, PostgreSQL, and microservices at scale.",
        )

        score = score_job(job, profile)
        tier = classify_tier(score, profile)

        assert score >= 3
        assert tier in {"standard", "high"}


class TestExclusions:
    def test_marketing_intern_excluded(self, profile) -> None:
        job = _job(
            title="Marketing Intern",
            department="Marketing",
            description="Support brand campaigns and social media for summer 2027.",
        )

        assert should_exclude(job, profile)

    def test_phd_intern_excluded(self, profile) -> None:
        job = _job(
            title="Research Intern",
            department="Research",
            description="Open to PhD students pursuing doctoral research in ML.",
        )

        assert should_exclude(job, profile)

    def test_firmware_intern_excluded(self, profile) -> None:
        job = _job(
            title="Firmware Engineering Intern",
            department="Hardware",
            description="Verilog and FPGA bring-up for embedded systems.",
        )

        assert should_exclude(job, profile)

    def test_business_development_intern_excluded(self, profile) -> None:
        job = _job(
            title="Business Development Intern, Berlin",
            department="Business & Sales",
            location="Berlin, Germany",
            company_name="Uber",
            description="Support the business development team in Europe.",
        )

        assert should_exclude(job, profile)

    def test_non_us_location_excluded(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="Paris, France",
            description="Build backend services.",
        )

        assert should_exclude(job, profile)

    def test_india_only_location_excluded(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="Bengaluru, Karnataka, India",
            description="Build backend services.",
        )

        assert should_exclude(job, profile)

    def test_vague_multi_location_allowed(self, profile) -> None:
        job = _job(
            title="Software Developer Internship - Undergraduate",
            department="Engineering",
            location="3 Locations",
            company_name="Blue Origin",
            description="Spring 2027 software internship.",
        )

        assert not should_exclude(job, profile)

    def test_city_only_location_allowed(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="San Jose",
            description="Build backend services.",
        )

        assert not should_exclude(job, profile)

    def test_canadian_province_without_country_excluded(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="Toronto, ON",
            description="Build backend services.",
        )

        assert should_exclude(job, profile)

    def test_puerto_rico_excluded(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="San Juan, Puerto Rico",
            description="Build backend services.",
        )

        assert should_exclude(job, profile)

    def test_mixed_us_and_foreign_location_allowed(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location=(
                "Mountain View, CA, USA; Waterloo, ON, Canada; "
                "Montreal, QC, Canada"
            ),
            description="Build backend services for summer 2027.",
        )

        assert not should_exclude(job, profile)

    def test_remote_foreign_only_excluded(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="Remote - India",
            description="Build backend services.",
        )

        assert should_exclude(job, profile)

    def test_remote_without_country_allowed(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="Remote",
            description="Build backend services.",
        )

        assert not should_exclude(job, profile)

    def test_us_state_location_allowed(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="San Francisco, CA",
            description="Build backend services.",
        )

        assert not should_exclude(job, profile)

    def test_workday_state_dash_city_location_allowed(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern",
            department="Engineering",
            location="California - San Francisco",
            description="Build backend services.",
        )

        assert not should_exclude(job, profile)


class TestPrestigeAndTierClassification:
    def test_swe_intern_summer_2027_at_tier_s_company(self, profile) -> None:
        job = _job(
            title="Software Engineering Intern — Summer 2027",
            department="Engineering",
            company_name="Google",
            description="Build scalable backend systems for Google Cloud.",
        )

        score = score_job(job, profile)

        assert score >= profile.alerts.high_score_threshold
        assert classify_tier(score, profile) == "high"
        assert not should_exclude(job, profile)

    def test_low_score_maps_to_standard_tier(self, profile) -> None:
        job = _job(
            title="Operations Intern",
            department="Operations",
            company_name="Unknown Startup",
            description="General business operations support.",
        )

        score = score_job(job, profile)
        assert score < profile.alerts.high_score_threshold
        assert classify_tier(score, profile) == "standard"

    @pytest.mark.parametrize(
        ("score", "expected"),
        [(0, "standard"), (6, "standard"), (7, "high"), (15, "high")],
    )
    def test_classify_tier_threshold(self, profile, score: int, expected: str) -> None:
        assert classify_tier(score, profile) == expected
