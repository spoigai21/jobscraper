"""Tests for Amazon Jobs search.json parser."""

from __future__ import annotations

import json
from pathlib import Path

from monitor.parsers.amazon import (
    amazon_search_json_url,
    is_amazon_jobs_url,
    parse_amazon,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestAmazonUrlHelpers:
    def test_detects_search_url(self) -> None:
        url = (
            "https://www.amazon.jobs/en/search?base_query=intern&country=USA"
            "&business_category[]=studentprograms&sort=recent"
        )
        assert is_amazon_jobs_url(url)

    def test_converts_to_search_json(self) -> None:
        url = (
            "https://www.amazon.jobs/en/search?base_query=intern&country=USA"
            "&business_category[]=studentprograms&sort=recent"
        )
        api_url = amazon_search_json_url(url, offset=100, result_limit=100)
        assert api_url.startswith("https://www.amazon.jobs/en/search.json?")
        assert "offset=100" in api_url
        assert "result_limit=100" in api_url
        assert "business_category%5B%5D=studentprograms" in api_url


class TestParseAmazon:
    def test_parses_sample_fixture(self) -> None:
        raw = json.loads(
            (_FIXTURES / "amazon_sample.json").read_text(encoding="utf-8")
        )
        jobs = parse_amazon(raw, "Amazon")

        assert len(jobs) == 2
        assert jobs[0].id == "10435122"
        assert "Tax Intern" in jobs[0].title
        assert jobs[0].location == "Seattle, Washington, USA"
        assert jobs[0].url == (
            "https://www.amazon.jobs/en/jobs/10435122/"
            "2027-tax-intern-summer-internship"
        )
        assert "Finance & Accounting" in jobs[0].department
        assert jobs[1].id == "10435672"
