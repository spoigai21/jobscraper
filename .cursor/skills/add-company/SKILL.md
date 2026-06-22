---
name: add-company
description: >-
  Add a new company to the internship monitor. Use when the user asks to add,
  monitor, track, or configure a new company, career page, or job board.
---

# Add Company

Add a company to `COMPANIES`, optionally to prestige tiers, and verify scraping works.

## Trigger phrases

- add company / new company / monitor [Company]
- track [Company] internships / add [Company] to the monitor
- configure career page for [Company]

## Overview

```
1. Discover scrapeable job-board API URL
2. Pick keywords + enabled flag
3. Add CompanyConfig to monitor/companies.py (copy similar entry)
4. Add to monitor/profile.yaml prestige tier (ask user if unknown)
5. Add test in tests/test_companies.py if board type is novel
6. Verify fetch + pytest
```

## Step 1: Discover the job board API

Career homepages are often JS SPAs. Find a **JSON API** the scraper can GET/POST.

### Inspect the careers site

1. Open the company's careers / university / intern search page in a browser.
2. DevTools → **Network** → filter XHR/Fetch → reload or search "intern".
3. Look for JSON responses with job titles/IDs.

### Common patterns in this repo

| Board | URL pattern | Parser | Example in `companies.py` |
|-------|-------------|--------|---------------------------|
| **Greenhouse** | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | `parse_greenhouse` | Anthropic, SpaceX, Waymo, Stripe |
| **Ashby** | `https://api.ashbyhq.com/posting-api/job-board/{slug}` | `parse_ashby` | OpenAI, Skydio, Notion, Ramp |
| **Lever** | `https://api.lever.co/v0/postings/{slug}?commitment=Internship%2FCo-op` | `parse_lever` | Zoox (`zoox`), Netflix (`netflix`) |
| **Workday** | `{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs?searchText=...` | `parse_workday` | Blue Origin, Visa, Salesforce |
| **Microsoft PCSX** | `https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=intern` | `parse_microsoft` | Microsoft |
| **Meta GraphQL** | `https://www.metacareers.com/jobsearch?q=intern` | `parse_meta` | Meta |
| **Uber JSON** | `https://www.uber.com/api/loadSearchJobsResults?localeCode=en&query=intern` | `parse_uber` | Uber |
| **HTML fallback** | Generic careers URL | hash-based HTML diff | Google, Apple (usually `enabled=False`) |

**Board detection:** `monitor/parsers/boards.py` → `detect_board_type(url)` maps URL substrings to `BoardType`. Match an existing pattern before adding a custom parser.

```bash
# Quick API probe (Greenhouse example)
curl -s "https://boards-api.greenhouse.io/v1/boards/spacex/jobs?content=true" | head -c 500

# Confirm board type
python -c "from monitor.parsers.boards import detect_board_type; print(detect_board_type('URL_HERE'))"
```

**Greenhouse slug discovery:** Board slug often differs from company name (e.g. DoorDash → `doordashusa`, Aurora → `aurorainnovation`, Anduril was `andurilindustries`). Try slug variants or inspect embed URLs on the careers page.

**When to set `enabled=False`:** API returns empty/403, page is JS-only, or bot protection blocks fetches. Document why in an inline comment (see Google, Tesla, Palantir entries).

## Step 2: Choose keywords

Shared lists at top of `monitor/companies.py`:

| Constant | Use when |
|----------|----------|
| `FILTERED_INTERN_KEYWORDS` | **Default** for JSON job boards (Greenhouse, Ashby, Lever, Workday) |
| `DEFAULT_KEYWORDS` | Broader HTML pages; includes bare `"intern"` and `"2027"` |
| `STRICT_INTERN_KEYWORDS` | Generic career homepages — avoids bare `"intern"` (matches "internal") |
| Custom list | Noisy boards — copy **SpaceX** pattern with specific phrases only |

SpaceX custom keywords (noisy board):

```python
keywords=[
    "intern program",
    "internship/co-op",
    "engineering intern",
    "software intern",
    "summer 2027",
],
```

Alerts fire when **any** keyword matches (not all).

## Step 3: Add CompanyConfig

Append to `COMPANIES` in `monitor/companies.py`. Copy the closest existing entry.

**Greenhouse template** (match Anthropic, Rocket Lab):

```python
CompanyConfig(
    name="NewCo",
    url="https://boards-api.greenhouse.io/v1/boards/newcoslug/jobs?content=true",
    keywords=FILTERED_INTERN_KEYWORDS,
    enabled=True,
),
```

**Ashby template** (match OpenAI):

```python
CompanyConfig(
    name="NewCo",
    url="https://api.ashbyhq.com/posting-api/job-board/newco",
    keywords=FILTERED_INTERN_KEYWORDS,
    enabled=True,
),
```

**Lever template** (match Zoox):

```python
CompanyConfig(
    name="NewCo",
    url="https://api.lever.co/v0/postings/newco?commitment=Internship%2FCo-op",
    keywords=FILTERED_INTERN_KEYWORDS,
    enabled=True,
),
```

**Workday template** (match Blue Origin):

```python
CompanyConfig(
    name="NewCo",
    url=(
        "https://newco.wd5.myworkdayjobs.com/wday/cxs/newco/NewCoSite/jobs"
        "?searchText=software engineering intern"
    ),
    keywords=FILTERED_INTERN_KEYWORDS,
    enabled=True,
),
```

Conventions:
- `name` — display name for alerts, CLI, prestige tiers (exact string matters everywhere)
- Inline `# comment` when `enabled=False` explaining why
- Keep alphabetical-ish grouping or place near similar companies

## Step 4: Prestige tier (profile.yaml)

Add under `prestige:` in `monitor/profile.yaml` if the company should affect relevance scoring:

```yaml
prestige:
  tier_s:  # Google, Meta, OpenAI, Anthropic — +4 score
  tier_a:  # Stripe, SpaceX, Waymo — +3
  tier_b:  # Zoox, Rocket Lab, NASA — +2
  tier_c:  # Ramp, DoorDash, Figma — +1
```

**If tier is unknown, ask the user** before assigning. Companies not in any tier get no prestige bonus (`tier_for_company` returns `None`).

Note: Snap, Adobe, ByteDance, TikTok appear in `tier_c` without `CompanyConfig` entries — prestige placeholders only.

## Step 5: Tests

For new board URLs, add a test class in `tests/test_companies.py` following existing patterns:

```python
class TestNewCoBoard:
    def test_uses_greenhouse_api(self) -> None:
        company = _company("NewCo")
        assert company.url == "https://boards-api.greenhouse.io/v1/boards/..."
        assert detect_board_type(company.url) == BoardType.GREENHOUSE
        assert company.enabled is True
```

Parser behavior is covered in `tests/test_scraper.py` with fixture companies (Waymo, Salesforce, etc.) — only add there for new **board types**, not every company.

## Step 6: Verify

### Fetch check

```bash
curl -s -o /dev/null -w "%{http_code}" "API_URL"
# Expect 200 with JSON body containing jobs
```

### CLI status (after monitor restart)

```bash
python cli.py status
# New company appears with En=yes/no matching enabled flag
```

### Run tests

```bash
pytest tests/test_companies.py
pytest  # full suite
```

### Optional live poll

Restart monitor (`python cli.py run` or `python main.py`) and confirm `OK   NewCo` in poll output (no `ERR`).

## Verification checklist

```
- [ ] API URL returns job JSON (not HTML shell or 403)
- [ ] detect_board_type(url) matches expected BoardType
- [ ] CompanyConfig added with correct name, url, keywords, enabled
- [ ] Prestige tier assigned (or user declined / unknown)
- [ ] test_companies.py updated if asserting board config
- [ ] pytest passes
- [ ] Do NOT commit unless user asks
```

## Reference files

| File | Role |
|------|------|
| `monitor/companies.py` | `COMPANIES` list — primary edit |
| `monitor/profile.yaml` | Prestige tiers for scoring |
| `monitor/parsers/boards.py` | `detect_board_type`, `parse_*` |
| `monitor/scraper.py` | Fetch + poll logic per board type |
| `monitor/models.py` | `CompanyConfig` dataclass |
| `monitor/cli.py` | `status`, `toggle` commands |
| `tests/test_companies.py` | Board URL/config smoke tests |
