"""Tests for Greenhouse, Ashby, and Lever job board parsers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_parser import (
    BoardType,
    JobPosting,
    detect_board_type,
    job_matches_keyword,
    jobs_to_text,
    parse_ashby,
    parse_greenhouse,
    parse_job_board,
    parse_lever,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestDetectBoardType:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
                BoardType.GREENHOUSE,
            ),
            (
                "https://api.ashbyhq.com/posting-api/job-board/skydio",
                BoardType.ASHBY,
            ),
            (
                "https://api.lever.co/v0/postings/zoox?mode=json",
                BoardType.LEVER,
            ),
            (
                "https://blueorigin.wd5.myworkdayjobs.com/wday/cxs/blueorigin/BlueOrigin/jobs",
                BoardType.WORKDAY,
            ),
            ("https://careers.google.com/jobs", BoardType.HTML),
        ],
    )
    def test_detects_board_from_url(self, url: str, expected: BoardType) -> None:
        assert detect_board_type(url) == expected


class TestParseGreenhouse:
    def test_parses_sample_fixture(self, greenhouse_json: dict) -> None:
        jobs = parse_greenhouse(greenhouse_json, "Waymo")

        assert len(jobs) == 2
        cv_job = jobs[0]
        assert isinstance(cv_job, JobPosting)
        assert cv_job.id == "4012345"
        assert cv_job.title == "Computer Vision Intern — Perception"
        assert cv_job.department == "Perception Engineering"
        assert cv_job.location == "Mountain View, CA"
        assert "YOLO" in cv_job.description
        assert "PyTorch" in cv_job.description
        assert cv_job.url.endswith("/4012345")
        assert cv_job.company_name == "Waymo"

    def test_strips_html_from_description(self, greenhouse_json: dict) -> None:
        jobs = parse_greenhouse(greenhouse_json, "Waymo")
        assert "<p>" not in jobs[0].description
        assert "<strong>" not in jobs[0].description

    def test_parses_raw_json_string(self) -> None:
        raw = (FIXTURES_DIR / "greenhouse_sample.json").read_text(encoding="utf-8")
        jobs = parse_greenhouse(raw, "Waymo")
        assert len(jobs) == 2


class TestParseAshby:
    def test_parses_sample_fixture(self, ashby_json: dict) -> None:
        jobs = parse_ashby(ashby_json, "Skydio")

        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == "a1b2c3d4-5678-90ab-cdef-1234567890ab"
        assert job.title == "Software Engineering Intern — Summer 2027"
        assert job.department == "Engineering"
        assert job.location == "San Francisco, CA"
        assert "FastAPI" in job.description
        assert "RAG" in job.description
        assert job.company_name == "Skydio"

    def test_prefers_plain_description(self, ashby_json: dict) -> None:
        jobs = parse_ashby(ashby_json, "Skydio")
        assert "health platform" in jobs[0].description.lower()


class TestParseLever:
    def test_parses_sample_fixture(self, lever_json: list) -> None:
        jobs = parse_lever(lever_json, "Zoox")

        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == "zoox-perception-2027"
        assert job.title == "Perception Software Intern"
        assert job.department == "Autonomy"
        assert job.location == "Foster City, CA"
        assert "computer vision" in job.description.lower()
        assert job.url == "https://jobs.lever.co/zoox/zoox-perception-2027"

    def test_parses_from_json_string(self) -> None:
        raw = (FIXTURES_DIR / "lever_sample.json").read_text(encoding="utf-8")
        jobs = parse_lever(raw, "Zoox")
        assert jobs[0].title == "Perception Software Intern"


class TestParseJobBoard:
    def test_routes_to_greenhouse_parser(self, greenhouse_json: dict) -> None:
        url = "https://boards-api.greenhouse.io/v1/boards/waymo/jobs"
        jobs = parse_job_board(greenhouse_json, url, "Waymo")
        assert len(jobs) == 2

    def test_routes_to_ashby_parser(self, ashby_json: dict) -> None:
        url = "https://api.ashbyhq.com/posting-api/job-board/skydio"
        jobs = parse_job_board(ashby_json, url, "Skydio")
        assert len(jobs) == 1

    def test_routes_to_lever_parser(self, lever_json: list) -> None:
        url = "https://api.lever.co/v0/postings/zoox"
        jobs = parse_job_board(lever_json, url, "Zoox")
        assert len(jobs) == 1


class TestJobHelpers:
    def test_jobs_to_text_includes_titles_and_descriptions(
        self, greenhouse_json: dict
    ) -> None:
        jobs = parse_greenhouse(greenhouse_json, "Waymo")
        text = jobs_to_text(jobs)

        assert "computer vision intern" in text
        assert "yolo" in text
        assert "internal communications" in text

    def test_job_matches_2027_seasonal_keyword(self, ashby_json: dict) -> None:
        jobs = parse_ashby(ashby_json, "Skydio")
        keywords = ["summer 2027", "intern", "internship"]

        assert job_matches_keyword(jobs[0], keywords) == "summer 2027"

    def test_job_matches_intern_word_boundary(self, greenhouse_json: dict) -> None:
        jobs = parse_greenhouse(greenhouse_json, "Waymo")
        intern_job = jobs[0]
        internal_job = jobs[1]

        assert job_matches_keyword(intern_job, ["intern"]) == "intern"
        assert job_matches_keyword(internal_job, ["intern"]) is None

    def test_job_matches_co_op_2027(self, lever_json: list) -> None:
        jobs = parse_lever(lever_json, "Zoox")
        assert job_matches_keyword(jobs[0], ["co-op 2027"]) == "co-op 2027"
