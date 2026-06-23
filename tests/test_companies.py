"""Tests for company board configuration."""

from __future__ import annotations

from monitor.companies import (
    COMPANIES,
    INTERN_CYCLE_KEYWORDS,
    INTERN_LEVEL_KEYWORDS,
    intern_cycle_keywords_for_year,
)
from monitor.parsers.boards import BoardType, detect_board_type


def _company(name: str):
    for company in COMPANIES:
        if company.name == name:
            return company
    raise AssertionError(f"Company not found: {name}")


class TestRelativityBoard:
    def test_uses_greenhouse_api(self) -> None:
        company = _company("Relativity")

        assert (
            company.url
            == "https://boards-api.greenhouse.io/v1/boards/relativity/jobs?content=true"
        )
        assert detect_board_type(company.url) == BoardType.GREENHOUSE
        assert company.enabled is True


class TestMetaBoard:
    def test_uses_graphql_jobsearch(self) -> None:
        company = _company("Meta")

        assert company.url == "https://www.metacareers.com/jobsearch?q=intern"
        assert detect_board_type(company.url) == BoardType.META
        assert company.enabled is True


class TestGoogleBoard:
    def test_uses_ssr_careers_search(self) -> None:
        company = _company("Google")

        assert company.url == (
            "https://careers.google.com/jobs/results/?employment_type=INTERN"
        )
        assert detect_board_type(company.url) == BoardType.GOOGLE
        assert company.enabled is True


class TestAmazonBoard:
    def test_uses_search_json_api(self) -> None:
        company = _company("Amazon")

        assert company.url == (
            "https://www.amazon.jobs/en/search?base_query=intern&country=USA"
            "&business_category[]=studentprograms&sort=recent"
        )
        assert detect_board_type(company.url) == BoardType.AMAZON
        assert company.enabled is True


class TestAppleBoard:
    def test_uses_hydration_search(self) -> None:
        company = _company("Apple")

        assert company.url == (
            "https://jobs.apple.com/en-us/search?search=internship&sort=newest"
        )
        assert detect_board_type(company.url) == BoardType.APPLE
        assert company.enabled is True


class TestNuroBoard:
    def test_uses_greenhouse_api(self) -> None:
        company = _company("Nuro")

        assert (
            company.url
            == "https://boards-api.greenhouse.io/v1/boards/nuro/jobs?content=true"
        )
        assert detect_board_type(company.url) == BoardType.GREENHOUSE
        assert company.enabled is True


class TestZooxBoard:
    def test_uses_lever_api(self) -> None:
        company = _company("Zoox")

        assert (
            company.url
            == "https://api.lever.co/v0/postings/zoox?commitment=Internship%2FCo-op"
        )
        assert detect_board_type(company.url) == BoardType.LEVER
        assert company.enabled is True


class TestPalantirBoard:
    def test_uses_lever_api(self) -> None:
        company = _company("Palantir")

        assert (
            company.url
            == "https://api.lever.co/v0/postings/palantir?commitment=Internship"
        )
        assert detect_board_type(company.url) == BoardType.LEVER
        assert company.enabled is True


class TestMobileyeBoard:
    def test_uses_lever_eu_api(self) -> None:
        company = _company("Mobileye")

        assert company.url == "https://api.eu.lever.co/v0/postings/mobileye"
        assert detect_board_type(company.url) == BoardType.LEVER
        assert company.enabled is True


class TestByteDanceBoard:
    def test_uses_atsx_api(self) -> None:
        company = _company("ByteDance")

        assert (
            company.url
            == "https://jobs.bytedance.com/api/v1/search/job/posts"
            "?keyword=intern&portal_type=2"
        )
        assert detect_board_type(company.url) == BoardType.BYTEDANCE
        assert company.enabled is True


class TestZiplineBoard:
    def test_uses_greenhouse_api(self) -> None:
        company = _company("Zipline")

        assert (
            company.url
            == "https://boards-api.greenhouse.io/v1/boards/flyzipline/jobs?content=true"
        )
        assert detect_board_type(company.url) == BoardType.GREENHOUSE
        assert company.enabled is True


class TestWingBoard:
    def test_uses_greenhouse_api(self) -> None:
        company = _company("Wing")

        assert (
            company.url
            == "https://boards-api.greenhouse.io/v1/boards/wing/jobs?content=true"
        )
        assert detect_board_type(company.url) == BoardType.GREENHOUSE
        assert company.enabled is True


class TestCloudflareBoard:
    def test_uses_greenhouse_api(self) -> None:
        company = _company("Cloudflare")

        assert (
            company.url
            == "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true"
        )
        assert detect_board_type(company.url) == BoardType.GREENHOUSE
        assert company.enabled is True


class TestSnapBoard:
    def test_uses_workday_api(self) -> None:
        company = _company("Snap")

        assert (
            company.url
            == "https://wd1.myworkdaysite.com/wday/cxs/snapchat/snap/jobs"
            "?searchText=software engineering intern"
        )
        assert detect_board_type(company.url) == BoardType.WORKDAY
        assert company.enabled is True


class TestAdobeBoard:
    def test_uses_workday_api(self) -> None:
        company = _company("Adobe")

        assert (
            company.url
            == "https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs"
            "?searchText=internship"
        )
        assert detect_board_type(company.url) == BoardType.WORKDAY
        assert company.enabled is True


class TestCrowdStrikeBoard:
    def test_uses_workday_api(self) -> None:
        company = _company("CrowdStrike")

        assert (
            company.url
            == "https://crowdstrike.wd5.myworkdayjobs.com/wday/cxs/crowdstrike/"
            "crowdstrikecareers/jobs?searchText=internship"
        )
        assert detect_board_type(company.url) == BoardType.WORKDAY
        assert company.enabled is True


class TestTikTokBoard:
    def test_uses_atsx_supplier_api(self) -> None:
        company = _company("TikTok")

        assert (
            company.url
            == "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
            "?keywords=intern"
        )
        assert detect_board_type(company.url) == BoardType.TIKTOK
        assert company.enabled is True


class TestNetflixBoard:
    def test_uses_eightfold_apply_v2_api(self) -> None:
        company = _company("Netflix")

        assert (
            company.url
            == "https://explore.jobs.netflix.net/api/apply/v2/jobs"
            "?domain=netflix.com&query=intern"
        )
        assert detect_board_type(company.url) == BoardType.MICROSOFT
        assert company.enabled is True


class TestNvidiaBoard:
    def test_uses_workday_api(self) -> None:
        company = _company("NVIDIA")

        assert (
            company.url
            == "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
            "?searchText=software engineering intern"
        )
        assert detect_board_type(company.url) == BoardType.WORKDAY
        assert company.enabled is True


class TestBloombergBoard:
    def test_uses_avature_html_search(self) -> None:
        company = _company("Bloomberg")

        assert company.url == (
            "https://bloomberg.avature.net/careers/SearchJobs"
            "?jobRecordsPerPage=50&jobOffset=0&search=internship"
        )
        assert detect_board_type(company.url) == BoardType.HTML
        assert company.enabled is True


class TestInternKeywordConfig:
    def test_cycle_keywords_include_bridge_and_seasons(self) -> None:
        cycle = intern_cycle_keywords_for_year(2027)
        assert "spring 2027" in cycle
        assert "summer 2027" in cycle
        assert "fall 2027" in cycle
        assert "co-op 2027" in cycle
        assert "2027" in cycle
        assert "winter 2026" in cycle

    def test_all_companies_use_two_list_keywords(self) -> None:
        for company in COMPANIES:
            assert company.level_keywords
            assert company.cycle_keywords
            assert company.cycle_keywords == INTERN_CYCLE_KEYWORDS
