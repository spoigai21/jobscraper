"""Tests for company board configuration."""

from __future__ import annotations

from monitor.companies import COMPANIES
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


class TestZooxBoard:
    def test_uses_lever_api(self) -> None:
        company = _company("Zoox")

        assert (
            company.url
            == "https://api.lever.co/v0/postings/zoox?commitment=Internship%2FCo-op"
        )
        assert detect_board_type(company.url) == BoardType.LEVER
        assert company.enabled is True
