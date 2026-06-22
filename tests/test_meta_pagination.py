"""Tests for Meta Careers multi-page fetch aggregation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from monitor.parsers.meta import MAX_META_PAGES, _extract_all_jobs, fetch_meta_search_raw

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _page_fixture(page: int) -> str:
    raw = json.loads((_FIXTURES / "meta_sample.json").read_text(encoding="utf-8"))
    jobs = raw["data"]["job_search_with_featured_jobs"]["all_jobs"]
    if page == 1:
        page_jobs = jobs[:2]
    elif page == 2:
        page_jobs = jobs[2:]
    else:
        page_jobs = []
    raw["data"]["job_search_with_featured_jobs"]["all_jobs"] = page_jobs
    return json.dumps(raw)


class TestMetaPagination:
    def test_extract_all_jobs_reads_fixture(self) -> None:
        text = (_FIXTURES / "meta_sample.json").read_text(encoding="utf-8")
        jobs = _extract_all_jobs(text)
        assert len(jobs) == 3

    def test_fetch_meta_search_raw_aggregates_pages(self) -> None:
        url = "https://www.metacareers.com/jobsearch?q=intern"
        search_html = (
            '<html><script>["LSD",[],{"token":"abc123"}]</script>'
            '"client_revision":12345,"hsi":"999"</html>'
        )
        graphql_responses = [
            MagicMock(text=_page_fixture(1), status_code=200),
            MagicMock(text=_page_fixture(2), status_code=200),
            MagicMock(text=_page_fixture(3), status_code=200),
        ]

        with patch("monitor.parsers.meta.requests.Session") as session_cls:
            session = session_cls.return_value
            session.get.return_value = MagicMock(
                text=search_html,
                status_code=200,
                raise_for_status=MagicMock(),
            )
            session.post.side_effect = graphql_responses

            raw = fetch_meta_search_raw(url, user_agent="test-agent", timeout=5)

        assert raw is not None
        payload = json.loads(raw)
        jobs = payload["data"]["job_search_with_featured_jobs"]["all_jobs"]
        assert len(jobs) == 3
        assert session.post.call_count == 3

    def test_fetch_meta_search_raw_respects_page_cap(self) -> None:
        url = "https://www.metacareers.com/jobsearch?q=intern"
        search_html = (
            '<html><script>["LSD",[],{"token":"abc123"}]</script>'
            '"client_revision":12345,"hsi":"999"</html>'
        )
        repeating_page = MagicMock(
            text=_page_fixture(1),
            status_code=200,
            raise_for_status=MagicMock(),
        )

        with patch("monitor.parsers.meta.requests.Session") as session_cls:
            session = session_cls.return_value
            session.get.return_value = MagicMock(
                text=search_html,
                status_code=200,
                raise_for_status=MagicMock(),
            )
            session.post.return_value = repeating_page

            raw = fetch_meta_search_raw(url, user_agent="test-agent", timeout=5)

        assert raw is not None
        assert session.post.call_count == MAX_META_PAGES
