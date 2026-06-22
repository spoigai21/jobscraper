"""Tests for Meta Careers GraphQL parser."""

from __future__ import annotations

import json
from pathlib import Path

from monitor.parsers.meta import (
    is_meta_company,
    is_meta_jobs_url,
    meta_search_query,
    parse_meta,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestIsMetaCompany:
    def test_recognizes_meta(self) -> None:
        assert is_meta_company("Meta")
        assert not is_meta_company("Microsoft")


class TestMetaUrlHelpers:
    def test_detects_jobsearch_url(self) -> None:
        assert is_meta_jobs_url("https://www.metacareers.com/jobsearch?q=intern")

    def test_extracts_search_query(self) -> None:
        url = "https://www.metacareers.com/jobsearch?q=software%20intern"
        assert meta_search_query(url) == "software intern"


class TestParseMetaGraphql:
    def test_parses_sample_fixture(self) -> None:
        raw = json.loads(
            (_FIXTURES / "meta_sample.json").read_text(encoding="utf-8")
        )
        jobs = parse_meta(raw, "Meta")

        assert len(jobs) == 3
        assert jobs[0].id == "1760132191666571"
        assert "Intern" in jobs[0].title
        assert jobs[0].location == "Redmond, WA"
        assert jobs[0].url.endswith("/1760132191666571/")
        assert "AI Research" in jobs[0].department
        assert "Machine Learning" in jobs[2].description
