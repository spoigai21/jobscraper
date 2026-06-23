"""Tests for Greenhouse, Ashby, and Lever job board parsers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor.models import JobPosting
from monitor.parsers.boards import (
    BoardType,
    detect_board_type,
    job_matches_keyword,
    jobs_to_text,
    parse_ashby,
    parse_bytedance,
    parse_greenhouse,
    parse_job_board,
    parse_lever,
    parse_microsoft,
    parse_uber,
    parse_workday,
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
            (
                "https://www.uber.com/api/loadSearchJobsResults?localeCode=en&query=intern",
                BoardType.UBER,
            ),
            (
                "https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=intern",
                BoardType.MICROSOFT,
            ),
            (
                "https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com&query=intern",
                BoardType.MICROSOFT,
            ),
            (
                "https://www.metacareers.com/jobsearch?q=intern",
                BoardType.META,
            ),
            (
                "https://jobs.bytedance.com/api/v1/search/job/posts?keyword=intern&portal_type=2",
                BoardType.BYTEDANCE,
            ),
            (
                "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts?keywords=intern",
                BoardType.TIKTOK,
            ),
            (
                "https://careers.google.com/jobs/results/?employment_type=INTERN",
                BoardType.GOOGLE,
            ),
            ("https://careers.google.com/jobs", BoardType.GOOGLE),
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


class TestParseUber:
    def test_parses_live_api_shape(self) -> None:
        raw = {
            "data": {
                "results": [
                    {
                        "id": 159600,
                        "title": "Business Development Intern, Berlin",
                        "team": "Business & Sales",
                        "department": "University",
                        "location": {
                            "city": "Berlin",
                            "countryName": "Germany",
                            "country": "DEU",
                        },
                        "description": "Support business development in Europe.",
                    }
                ]
            }
        }
        jobs = parse_uber(raw, "Uber")

        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == "159600"
        assert job.title == "Business Development Intern, Berlin"
        assert job.department == "Business & Sales"
        assert job.location == "Berlin, Germany"
        assert job.url.endswith("/159600")
        assert job.company_name == "Uber"

    def test_routes_to_uber_parser(self) -> None:
        raw = {
            "data": {
                "results": [
                    {
                        "id": 42,
                        "title": "Software Engineering Intern",
                        "team": "Engineering",
                        "location": {"city": "San Francisco", "countryName": "United States"},
                        "description": "Build services.",
                    }
                ]
            }
        }
        url = "https://www.uber.com/api/loadSearchJobsResults?localeCode=en&query=intern"
        jobs = parse_job_board(raw, url, "Uber")
        assert len(jobs) == 1
        assert jobs[0].title == "Software Engineering Intern"


class TestParseByteDance:
    def test_parses_live_api_shape(self) -> None:
        raw = {
            "data": {
                "job_post_list": [
                    {
                        "id": "7604788487364544821",
                        "title": "Software Engineer Intern, Backend",
                        "description": "Build backend services for TikTok.",
                        "requirement": "Pursuing a BS in Computer Science.",
                        "job_category": {"en_name": "Engineering"},
                        "city_info": {"en_name": "San Jose"},
                    }
                ]
            }
        }
        jobs = parse_bytedance(raw, "ByteDance")

        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == "7604788487364544821"
        assert job.title == "Software Engineer Intern, Backend"
        assert job.department == "Engineering"
        assert job.location == "San Jose"
        assert "TikTok" in job.description
        assert job.url == "https://joinbytedance.com/search/7604788487364544821"
        assert job.company_name == "ByteDance"

    def test_routes_to_bytedance_parser(self) -> None:
        raw = {
            "data": {
                "job_post_list": [
                    {
                        "id": "123",
                        "title": "Machine Learning Intern",
                        "description": "Train models.",
                        "job_category": {"en_name": "Research"},
                        "city_info": {"en_name": "Seattle"},
                    }
                ]
            }
        }
        url = (
            "https://jobs.bytedance.com/api/v1/search/job/posts"
            "?keyword=intern&portal_type=2"
        )
        jobs = parse_job_board(raw, url, "ByteDance")
        assert len(jobs) == 1
        assert jobs[0].title == "Machine Learning Intern"


class TestParseMicrosoft:
    @pytest.fixture
    def microsoft_json(self) -> dict:
        return json.loads(
            (FIXTURES_DIR / "microsoft_sample.json").read_text(encoding="utf-8")
        )

    def test_parses_sample_fixture(self, microsoft_json: dict) -> None:
        board_url = (
            "https://apply.careers.microsoft.com/api/pcsx/search"
            "?domain=microsoft.com&query=intern"
        )
        jobs = parse_microsoft(microsoft_json, "Microsoft", board_url=board_url)

        assert len(jobs) == 3
        intern_job = jobs[1]
        assert intern_job.id == "1970393556864498"
        assert intern_job.title == "Research Intern - AI Frontiers"
        assert intern_job.department == "Applied Sciences"
        assert intern_job.location == "United States, Washington, Redmond"
        assert intern_job.url.endswith("/careers/job/1970393556864498")
        assert intern_job.company_name == "Microsoft"
        assert "Research Internships at Microsoft" in intern_job.description

    def test_parses_aggregated_fetch_payload(self) -> None:
        raw = {
            "positions": [
                {
                    "id": 123,
                    "name": "Software Engineering Intern",
                    "department": "Engineering",
                    "locations": ["Redmond, WA"],
                    "positionUrl": "/careers/job/123",
                }
            ],
            "count": 1,
        }
        jobs = parse_microsoft(raw, "Microsoft")
        assert len(jobs) == 1
        assert jobs[0].title == "Software Engineering Intern"

    def test_routes_to_microsoft_parser(self, microsoft_json: dict) -> None:
        url = (
            "https://apply.careers.microsoft.com/api/pcsx/search"
            "?domain=microsoft.com&query=intern"
        )
        jobs = parse_job_board(microsoft_json, url, "Microsoft")
        assert len(jobs) == 3


class TestParseNetflix:
    @pytest.fixture
    def netflix_json(self) -> dict:
        return json.loads(
            (FIXTURES_DIR / "netflix_sample.json").read_text(encoding="utf-8")
        )

    def test_parses_sample_fixture(self, netflix_json: dict) -> None:
        board_url = (
            "https://explore.jobs.netflix.net/api/apply/v2/jobs"
            "?domain=netflix.com&query=intern"
        )
        jobs = parse_microsoft(netflix_json, "Netflix", board_url=board_url)

        assert len(jobs) == 2
        intern_job = jobs[0]
        assert intern_job.id == "790315673635"
        assert intern_job.title.startswith("Video Algorithms Intern")
        assert intern_job.department == "Engineering"
        assert intern_job.location == "Los Gatos,California,United States of America"
        assert intern_job.url == "https://explore.jobs.netflix.net/careers/job/790315673635"
        assert intern_job.company_name == "Netflix"
        assert "video algorithms team" in intern_job.description

    def test_routes_to_microsoft_parser(self, netflix_json: dict) -> None:
        url = (
            "https://explore.jobs.netflix.net/api/apply/v2/jobs"
            "?domain=netflix.com&query=intern"
        )
        jobs = parse_job_board(netflix_json, url, "Netflix")
        assert len(jobs) == 2
        assert jobs[1].url.endswith("/careers/job/790315673636")


class TestParseMeta:
    def test_routes_to_meta_parser(self) -> None:
        raw = json.loads(
            (FIXTURES_DIR / "meta_sample.json").read_text(encoding="utf-8")
        )
        url = "https://www.metacareers.com/jobsearch?q=intern"
        jobs = parse_job_board(raw, url, "Meta")
        assert len(jobs) == 3
        assert jobs[0].company_name == "Meta"


class TestParseAmazon:
    def test_routes_to_amazon_parser(self) -> None:
        raw = json.loads(
            (FIXTURES_DIR / "amazon_sample.json").read_text(encoding="utf-8")
        )
        url = (
            "https://www.amazon.jobs/en/search?base_query=intern&country=USA"
            "&business_category[]=studentprograms&sort=recent"
        )
        jobs = parse_job_board(raw, url, "Amazon")
        assert len(jobs) == 2
        assert jobs[0].company_name == "Amazon"
        assert jobs[0].id == "10435122"


class TestParseGoogle:
    def test_parses_sample_fixture(self) -> None:
        from monitor.parsers.google import parse_google_html

        html = (FIXTURES_DIR / "google_sample.html").read_text(encoding="utf-8")
        jobs = parse_google_html(html, "Google")

        assert len(jobs) == 2
        assert jobs[0].id == "140245524367188678"
        assert jobs[0].company_name == "Google"
        assert "Student Researcher" in jobs[0].title

    def test_routes_to_google_parser(self) -> None:
        html = (FIXTURES_DIR / "google_sample.html").read_text(encoding="utf-8")
        url = "https://careers.google.com/jobs/results/?employment_type=INTERN"
        jobs = parse_job_board(html, url, "Google")
        assert len(jobs) == 2
        assert jobs[0].id == "140245524367188678"


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

    def test_routes_to_workday_parser(self) -> None:
        raw = {
            "jobPostings": [
                {
                    "title": "Data Science Intern",
                    "externalPath": "/job/Remote/Data-Science-Intern_JR789",
                    "locationsText": "Remote",
                    "bulletFields": ["JR789"],
                }
            ]
        }
        url = "https://blueorigin.wd5.myworkdayjobs.com/wday/cxs/blueorigin/BlueOrigin/jobs"
        jobs = parse_job_board(raw, url, "Blue Origin")
        assert len(jobs) == 1
        assert jobs[0].id == "JR789"


class TestParseWorkday:
    def test_parses_workday_postings(self) -> None:
        raw = {
            "total": 2,
            "jobPostings": [
                {
                    "title": "Software Engineering Intern",
                    "externalPath": "/job/California/Software-Engineering-Intern_JR123",
                    "locationsText": "California - San Francisco",
                    "bulletFields": ["JR123"],
                },
                {
                    "title": "Project Lead",
                    "externalPath": "/job/California/Project-Lead_JR456",
                    "locationsText": "California - San Francisco",
                    "bulletFields": ["JR456"],
                },
            ],
        }
        url = (
            "https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/"
            "External_Career_Site/jobs?searchText=internship"
        )
        jobs = parse_workday(raw, "Salesforce", board_url=url)

        assert len(jobs) == 2
        intern_job = jobs[0]
        assert intern_job.id == "JR123"
        assert intern_job.title == "Software Engineering Intern"
        assert intern_job.location == "California - San Francisco"
        assert intern_job.url.endswith("/Software-Engineering-Intern_JR123")
        assert intern_job.company_name == "Salesforce"


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
