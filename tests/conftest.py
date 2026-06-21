"""Shared pytest fixtures for the internship monitor test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor.profile import load_profile

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def profile():
    return load_profile()


@pytest.fixture
def greenhouse_json() -> dict:
    return json.loads((FIXTURES_DIR / "greenhouse_sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def ashby_json() -> dict:
    return json.loads((FIXTURES_DIR / "ashby_sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def lever_json() -> list:
    return json.loads((FIXTURES_DIR / "lever_sample.json").read_text(encoding="utf-8"))
