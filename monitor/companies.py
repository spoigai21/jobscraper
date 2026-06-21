"""Company careers pages to monitor for internship listings."""

from __future__ import annotations

from monitor.models import CompanyConfig

DEFAULT_KEYWORDS: list[str] = [
    "intern",
    "internship",
    "2027",
    "spring 2027",
    "summer 2027",
    "fall 2027",
    "co-op 2027",
    "co-op",
    "residency",
]

# Pre-filtered internship job boards: seasonal phrases reduce footer/copyright noise.
FILTERED_INTERN_KEYWORDS: list[str] = [
    "intern",
    "internship",
    "spring 2027",
    "summer 2027",
    "fall 2027",
    "co-op 2027",
    "co-op",
    "residency",
]

# Generic career homepages: avoid bare "intern" (matches "internal") and bare years.
STRICT_INTERN_KEYWORDS: list[str] = [
    "internship",
    "summer intern",
    "engineering intern",
    "software intern",
    "spring 2027",
    "summer 2027",
    "fall 2027",
    "co-op 2027",
    "co-op",
    "residency",
]

COMPANIES: list[CompanyConfig] = [
    CompanyConfig(
        name="Google",
        url="https://careers.google.com/jobs/results/?employment_type=INTERN",
        keywords=DEFAULT_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Meta",
        url="https://www.metacareers.com/jobsearch/",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=False,  # Greenhouse board 404; no public JSON job-search API (Comet GraphQL)
    ),
    CompanyConfig(
        name="Amazon",
        url="https://www.amazon.jobs/en/search?base_query=intern",
        keywords=DEFAULT_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Apple",
        url="https://jobs.apple.com/en-us/search?search=intern&sort=newest",
        keywords=STRICT_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="OpenAI",
        url="https://api.ashbyhq.com/posting-api/job-board/openai",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Anthropic",
        url="https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Microsoft",
        url="https://careers.microsoft.com/us/en/search-results?keywords=intern",
        keywords=STRICT_INTERN_KEYWORDS,
        enabled=False,  # SPA (Eightfold); listings load via JS, not in static HTML
    ),
    CompanyConfig(
        name="Uber",
        url="https://www.uber.com/api/loadSearchJobsResults?localeCode=en&query=intern",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,  # Greenhouse board 404; careers search JSON API (POST)
    ),
    CompanyConfig(
        name="Waymo",
        url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Skydio",
        url="https://api.ashbyhq.com/posting-api/job-board/skydio",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Zoox",
        url="https://jobs.lever.co/zoox?commitment=Internship%2FCo-op",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Cruise",
        url="https://getcruise.com/careers/jobs/",
        keywords=DEFAULT_KEYWORDS,
        enabled=False,  # GM wound down Cruise robotaxi; careers redirect to GM marketing
    ),
    CompanyConfig(
        name="Luminar",
        url="https://www.luminartech.com/careers/",
        keywords=DEFAULT_KEYWORDS,
        enabled=False,  # /careers/ redirects to a broken page; site is product marketing only
    ),
    CompanyConfig(
        name="Matterport",
        url="https://matterport.com/careers",
        keywords=DEFAULT_KEYWORDS,
        enabled=False,  # Redirects to CoStar Group portal — noisy, not Matterport-specific
    ),
    CompanyConfig(
        name="SpaceX",
        url="https://boards-api.greenhouse.io/v1/boards/spacex/jobs?content=true",
        keywords=[
            "intern program",
            "internship/co-op",
            "engineering intern",
            "software intern",
            "summer 2027",
        ],
        enabled=True,
    ),
    CompanyConfig(
        name="Rocket Lab",
        url="https://boards-api.greenhouse.io/v1/boards/rocketlab/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Blue Origin",
        url=(
            "https://blueorigin.wd5.myworkdayjobs.com/wday/cxs/blueorigin/BlueOrigin/jobs"
            "?searchText=software engineering intern"
        ),
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Visa",
        url=(
            "https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa/jobs"
            "?searchText=software engineering intern"
        ),
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Planet Labs",
        url="https://boards-api.greenhouse.io/v1/boards/planetlabs/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Relativity",
        url="https://www.relativityspace.com/internship-positions",
        keywords=[
            "internship",
            "engineering intern",
            "summer 2027",
            "accepting applications",
        ],
        enabled=True,
    ),
    CompanyConfig(
        name="Firefly",
        url="https://fireflyspace.com/careers/",
        keywords=STRICT_INTERN_KEYWORDS,
        enabled=False,  # WordPress careers page embeds listings via JS; section is empty in HTML
    ),
    CompanyConfig(
        name="Muon Space",
        url="https://boards-api.greenhouse.io/v1/boards/muonspace/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Astranis",
        url="https://boards-api.greenhouse.io/v1/boards/astranis/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Air Space Intelligence",
        url="https://www.airspace-intelligence.com/careers",
        keywords=STRICT_INTERN_KEYWORDS,
        enabled=False,  # Marketing careers page has no scrapeable job listings or intern keywords
    ),
    CompanyConfig(
        name="Scale AI",
        url="https://boards-api.greenhouse.io/v1/boards/scaleai/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,  # Greenhouse API (scale.com/careers/university is Next.js SPA)
    ),
    CompanyConfig(
        name="NVIDIA",
        url="https://jobs.nvidia.com/careers?filter_job_type=intern+%28fixed+term%29",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Stripe",
        url="https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Databricks",
        url="https://boards-api.greenhouse.io/v1/boards/databricks/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Datadog",
        url="https://boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Snowflake",
        url="https://api.ashbyhq.com/posting-api/job-board/snowflake",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Notion",
        url="https://api.ashbyhq.com/posting-api/job-board/notion",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Robinhood",
        url="https://boards-api.greenhouse.io/v1/boards/robinhood/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Netflix",
        url="https://api.lever.co/v0/postings/netflix",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=False,  # Lever API returns []; explore.jobs.netflix.net is JS-rendered
    ),
    CompanyConfig(
        name="LinkedIn",
        url="https://boards-api.greenhouse.io/v1/boards/linkedin/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Salesforce",
        url=(
            "https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/"
            "External_Career_Site/jobs?searchText=internship"
        ),
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Pinterest",
        url="https://boards-api.greenhouse.io/v1/boards/pinterest/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Coinbase",
        url="https://boards-api.greenhouse.io/v1/boards/coinbase/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Figma",
        url="https://boards-api.greenhouse.io/v1/boards/figma/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="DoorDash",
        url="https://boards-api.greenhouse.io/v1/boards/doordashusa/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Lyft",
        url="https://boards-api.greenhouse.io/v1/boards/lyft/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Cloudflare",
        url="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="MongoDB",
        url="https://boards-api.greenhouse.io/v1/boards/mongodb/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Nuro",
        url="https://www.nuro.ai/early-career",
        keywords=[
            "intern",
            "internship",
            "pathfinders",
            "summer 2027",
        ],
        enabled=True,
    ),
    CompanyConfig(
        name="Discord",
        url="https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Reddit",
        url="https://boards-api.greenhouse.io/v1/boards/reddit/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Airbnb",
        url="https://boards-api.greenhouse.io/v1/boards/airbnb/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,  # Greenhouse JSON; job links resolve to careers.airbnb.com/positions/
    ),
    CompanyConfig(
        name="Brex",
        url="https://boards-api.greenhouse.io/v1/boards/brex/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Instacart",
        url="https://boards-api.greenhouse.io/v1/boards/instacart/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Anduril",
        url="https://boards-api.greenhouse.io/v1/boards/andurilindustries/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Aurora",
        url="https://boards-api.greenhouse.io/v1/boards/aurorainnovation/jobs?content=true",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Applied Intuition",
        url="https://api.ashbyhq.com/posting-api/job-board/applied",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Plaid",
        url="https://api.ashbyhq.com/posting-api/job-board/plaid",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Ramp",
        url="https://api.ashbyhq.com/posting-api/job-board/ramp",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="NASA",
        url="https://intern.nasa.gov/ossi/web/public/main/index.cfm",
        keywords=DEFAULT_KEYWORDS,
        enabled=False,  # Site blocks automated requests; needs custom scraper
    ),
    CompanyConfig(
        name="JPL",
        url="https://www.jpl.nasa.gov/careers/internships/",
        keywords=STRICT_INTERN_KEYWORDS,
        enabled=False,  # NASA site blocks automated fetches (403)
    ),
    CompanyConfig(
        name="Palantir",
        url="https://jobs.lever.co/palantir?commitment=Internship",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=False,  # Lever HTML page; no JSON postings endpoint
    ),
    CompanyConfig(
        name="Tesla",
        url="https://www.tesla.com/careers/search/?type=3&query=intern",
        keywords=STRICT_INTERN_KEYWORDS,
        enabled=False,  # Blocks automated requests (403)
    ),
]
