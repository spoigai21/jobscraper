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
    parse_uber,
    parse_workday,
)
from monitor.parsers.nasa import (
    is_nasa_company,
    nasa_jobs_to_text,
    parse_nasa_html,
)

__all__ = [
    "BoardType",
    "detect_board_type",
    "format_new_jobs_snippet",
    "is_nasa_company",
    "job_matches_keyword",
    "jobs_to_text",
    "nasa_jobs_to_text",
    "parse_ashby",
    "parse_greenhouse",
    "parse_job_board",
    "parse_lever",
    "parse_nasa_html",
    "parse_uber",
    "parse_workday",
]
