"""Job board and site-specific listing parsers."""

from monitor.parsers.boards import (
    BoardType,
    detect_board_type,
    format_new_jobs_snippet,
    job_matches_keyword,
    jobs_to_text,
    parse_ashby,
    parse_greenhouse,
    parse_job_board,
    parse_lever,
    parse_meta,
    parse_microsoft,
    parse_uber,
    parse_workday,
)
from monitor.parsers.meta import (
    fetch_meta_search_raw,
    is_meta_company,
    is_meta_jobs_url,
)
from monitor.parsers.html import parse_html_jobs
from monitor.parsers.nasa import (
    is_nasa_company,
    nasa_jobs_to_text,
    parse_nasa_html,
)
from monitor.parsers.tesla import (
    TeslaScraper,
    is_tesla_company,
    parse_tesla_state,
    tesla_jobs_to_text,
)

__all__ = [
    "BoardType",
    "TeslaScraper",
    "detect_board_type",
    "fetch_meta_search_raw",
    "format_new_jobs_snippet",
    "is_meta_company",
    "is_meta_jobs_url",
    "is_nasa_company",
    "is_tesla_company",
    "job_matches_keyword",
    "jobs_to_text",
    "nasa_jobs_to_text",
    "parse_ashby",
    "parse_greenhouse",
    "parse_html_jobs",
    "parse_job_board",
    "parse_lever",
    "parse_meta",
    "parse_microsoft",
    "parse_nasa_html",
    "parse_tesla_state",
    "parse_uber",
    "parse_workday",
    "tesla_jobs_to_text",
]
