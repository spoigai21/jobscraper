"""Tests for HTML career page job parsing and keyword extraction."""

from __future__ import annotations

from monitor.companies import INTERN_CYCLE_KEYWORDS, INTERN_LEVEL_KEYWORDS
from monitor.notification_keywords import select_notification_keywords
from monitor.parsers.boards import job_matches_keyword, job_matches_level_and_cycle
from monitor.parsers.html import parse_html_jobs
from monitor.profile import load_profile


_LEVER_HTML = """
<html><body>
  <div class="posting" data-qa-posting-id="abc-123">
    <a href="https://jobs.lever.co/palantir/abc-123" class="posting-title">
      <h5>Software Engineering Intern - Summer 2027</h5>
    </a>
    <div class="posting-categories">
      <span>Engineering</span>
      <span>Denver, CO</span>
      <span>Internship</span>
    </div>
    <div class="posting-description">
      Build backend services with <strong>Python</strong> and <strong>FastAPI</strong>.
    </div>
  </div>
</body></html>
"""

_GREENHOUSE_HTML = """
<html><body>
  <section id="positions">
    <div class="opening" data-id="555">
      <a href="https://boards.greenhouse.io/example/jobs/555">Perception Intern</a>
      <span class="location">San Francisco</span>
      <span class="department">Autonomy</span>
      <p class="opening-description">Work on computer vision pipelines using PyTorch.</p>
    </div>
  </section>
</body></html>
"""


class TestParseHtmlJobs:
    def test_parses_lever_postings(self) -> None:
        jobs = parse_html_jobs(
            _LEVER_HTML,
            "https://jobs.lever.co/palantir?commitment=Internship",
            "Palantir",
        )

        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == "abc-123"
        assert "Summer 2027" in job.title
        assert job.department == "Engineering"
        assert job.location == "Denver, CO"
        assert "Python" in job.description
        assert "FastAPI" in job.description

    def test_parses_greenhouse_openings(self) -> None:
        jobs = parse_html_jobs(
            _GREENHOUSE_HTML,
            "https://boards.greenhouse.io/example",
            "ExampleCo",
        )

        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == "555"
        assert job.title == "Perception Intern"
        assert job.location == "San Francisco"
        assert "PyTorch" in job.description

    def test_returns_empty_for_unrecognized_html(self) -> None:
        html = "<html><body><p>No listings here</p></body></html>"
        assert parse_html_jobs(html, "https://example.com/careers", "ExampleCo") == []


class TestHtmlKeywordExtraction:
    def test_lever_job_matches_cycle_and_level_keywords(self) -> None:
        jobs = parse_html_jobs(_LEVER_HTML, "https://jobs.lever.co/palantir", "Palantir")

        assert (
            job_matches_level_and_cycle(
                jobs[0], INTERN_LEVEL_KEYWORDS, INTERN_CYCLE_KEYWORDS
            )
            == "summer 2027"
        )
        assert job_matches_keyword(jobs[0], ["intern"]) == "intern"

    def test_notification_keywords_include_cycle_and_tech(self) -> None:
        jobs = parse_html_jobs(_LEVER_HTML, "https://jobs.lever.co/palantir", "Palantir")
        profile = load_profile()
        job = jobs[0]
        searchable = " ".join(
            (job.title, job.department, job.location, job.description)
        )
        selected = select_notification_keywords(
            searchable,
            profile=profile,
            trigger_keyword="intern",
        )

        lowered = {term.lower() for term in selected}
        assert "summer 2027" in lowered or "intern" in lowered
        assert "python" in lowered or "fastapi" in lowered
