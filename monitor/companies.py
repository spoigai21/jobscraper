"""Company careers pages to monitor for internship listings."""

from __future__ import annotations

from monitor.models import CompanyConfig

def intern_cycle_keywords_for_year(year: int) -> list[str]:
    """Seasonal phrases, bare year, and prior-winter bridge for target cycle."""
    return [
        f"spring {year}",
        f"summer {year}",
        f"fall {year}",
        f"co-op {year}",
        str(year),
        f"winter {year - 1}",
    ]


INTERN_CYCLE_KEYWORDS: list[str] = intern_cycle_keywords_for_year(2027)

INTERN_LEVEL_KEYWORDS: list[str] = [
    "intern",
    "internship",
    "co-op",
    "residency",
    "undergraduate",
    "pursuing undergraduate",
]

STRICT_INTERN_LEVEL_KEYWORDS: list[str] = [
    "internship",
    "summer intern",
    "engineering intern",
    "software intern",
    "undergraduate",
    "pursuing undergraduate",
]

SPACEX_INTERN_LEVEL_KEYWORDS: list[str] = [
    "intern program",
    "internship/co-op",
    "engineering intern",
    "software intern",
]

COMPANIES: list[CompanyConfig] = [
    CompanyConfig(
        name="Google",
        url="https://careers.google.com/jobs/results/?employment_type=INTERN",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # SSR embeds intern listings in AF_initDataCallback ds:1
    ),
    CompanyConfig(
        name="HubSpot",
        url="https://wtcfns.hubspot.com/careers/graphql",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # GraphQL jobs query; Greenhouse board (hubspot) is empty
    ),
    CompanyConfig(
        name="Meta",
        url="https://www.metacareers.com/jobsearch?q=intern",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Comet GraphQL job search (CareersJobSearchResultsDataQuery)
    ),
    CompanyConfig(
        name="Amazon",
        url=(
            "https://www.amazon.jobs/en/search?base_query=intern&country=USA"
            "&business_category[]=studentprograms&sort=recent"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # search.json API (paginated by offset, result_limit=100)
    ),
    CompanyConfig(
        name="Apple",
        url="https://jobs.apple.com/en-us/search?search=internship&sort=newest",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # SSR hydration searchResults (paginated GET HTML)
    ),
    CompanyConfig(
        name="OpenAI",
        url="https://api.ashbyhq.com/posting-api/job-board/openai",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Anthropic",
        url="https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Microsoft",
        url=(
            "https://apply.careers.microsoft.com/api/pcsx/search"
            "?domain=microsoft.com&query=intern"
        ),
        level_keywords=STRICT_INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Eightfold PCSX search API (GET, paginated)
    ),
    CompanyConfig(
        name="Uber",
        url="https://www.uber.com/api/loadSearchJobsResults?localeCode=en&query=intern",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Greenhouse board 404; careers search JSON API (POST, max 100 results)
    ),
    CompanyConfig(
        name="Waymo",
        url="https://boards-api.greenhouse.io/v1/boards/waymo/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Wing",
        url="https://boards-api.greenhouse.io/v1/boards/wing/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Skydio",
        url="https://api.ashbyhq.com/posting-api/job-board/skydio",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Shield AI",
        url="https://api.lever.co/v0/postings/shieldai",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Lever API; jobs.lever.co/shieldai; commitment filter returns []
    ),
    CompanyConfig(
        name="Zoox",
        url="https://api.lever.co/v0/postings/zoox?commitment=Internship%2FCo-op",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Zipline",
        url="https://boards-api.greenhouse.io/v1/boards/flyzipline/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    # REMOVED — Luminar: liquidated Apr 2026; no scrapeable careers board
    # REMOVED — Matterport: redirects to CoStar Group portal — noisy, not Matterport-specific
    CompanyConfig(
        name="SpaceX",
        url="https://boards-api.greenhouse.io/v1/boards/spacex/jobs?content=true",
        level_keywords=SPACEX_INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Rocket Lab",
        url="https://boards-api.greenhouse.io/v1/boards/rocketlab/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Blue Origin",
        url=(
            "https://blueorigin.wd5.myworkdayjobs.com/wday/cxs/blueorigin/BlueOrigin/jobs"
            "?searchText=software engineering intern"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Bloomberg",
        url=(
            "https://bloomberg.avature.net/careers/SearchJobs"
            "?jobRecordsPerPage=50&jobOffset=0&search=internship"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Avature HTML search (GET; internship filter via search=)
    ),
    CompanyConfig(
        name="Visa",
        url=(
            "https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa/jobs"
            "?searchText=software engineering intern"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Planet Labs",
        url="https://boards-api.greenhouse.io/v1/boards/planetlabs/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Relativity",
        url="https://boards-api.greenhouse.io/v1/boards/relativity/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Greenhouse API; internship-positions page is Squarespace marketing
    ),
    # REMOVED — Firefly: WordPress careers page embeds listings via JS
    CompanyConfig(
        name="Muon Space",
        url="https://boards-api.greenhouse.io/v1/boards/muonspace/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Astranis",
        url="https://boards-api.greenhouse.io/v1/boards/astranis/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    # REMOVED — Air Space Intelligence: marketing careers page, no scrapeable listings
    CompanyConfig(
        name="Scale AI",
        url="https://boards-api.greenhouse.io/v1/boards/scaleai/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Greenhouse API (scale.com/careers/university is Next.js SPA)
    ),
    CompanyConfig(
        name="NVIDIA",
        url=(
            "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
            "?searchText=software engineering intern"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Workday cxs API (jobs.nvidia.com Eightfold SPA is wrong layer)
    ),
    CompanyConfig(
        name="Stripe",
        url="https://boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    # REMOVED — Symbotic: Workday cxs API (wd504; symbotic.wd1 redirects to maintenance)
    CompanyConfig(
        name="Databricks",
        url="https://boards-api.greenhouse.io/v1/boards/databricks/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Datadog",
        url="https://boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Snowflake",
        url="https://api.ashbyhq.com/posting-api/job-board/snowflake",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Notion",
        url="https://api.ashbyhq.com/posting-api/job-board/notion",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Robinhood",
        url="https://boards-api.greenhouse.io/v1/boards/robinhood/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Netflix",
        url=(
            "https://explore.jobs.netflix.net/api/apply/v2/jobs"
            "?domain=netflix.com&query=intern"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Eightfold apply v2 API (GET, paginated); Lever board empty
    ),
    CompanyConfig(
        name="Neuralink",
        url="https://boards-api.greenhouse.io/v1/boards/neuralink/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="LinkedIn",
        url="https://boards-api.greenhouse.io/v1/boards/linkedin/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Salesforce",
        url=(
            "https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/"
            "External_Career_Site/jobs?searchText=internship"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Pinterest",
        url="https://boards-api.greenhouse.io/v1/boards/pinterest/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Coinbase",
        url="https://boards-api.greenhouse.io/v1/boards/coinbase/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Figma",
        url="https://boards-api.greenhouse.io/v1/boards/figma/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="DoorDash",
        url="https://boards-api.greenhouse.io/v1/boards/doordashusa/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Lyft",
        url="https://boards-api.greenhouse.io/v1/boards/lyft/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Cloudflare",
        url="https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="CrowdStrike",
        url=(
            "https://crowdstrike.wd5.myworkdayjobs.com/wday/cxs/crowdstrike/"
            "crowdstrikecareers/jobs?searchText=internship"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="MongoDB",
        url="https://boards-api.greenhouse.io/v1/boards/mongodb/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Nuro",
        url="https://boards-api.greenhouse.io/v1/boards/nuro/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Discord",
        url="https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Snap",
        url=(
            "https://wd1.myworkdaysite.com/wday/cxs/snapchat/snap/jobs"
            "?searchText=software engineering intern"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Reddit",
        url="https://boards-api.greenhouse.io/v1/boards/reddit/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Adobe",
        url=(
            "https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs"
            "?searchText=internship"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Workday cxs API; careers.adobe.com is Phenom SPA front-end
    ),
    CompanyConfig(
        name="Airbnb",
        url="https://boards-api.greenhouse.io/v1/boards/airbnb/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Greenhouse JSON; job links resolve to careers.airbnb.com/positions/
    ),
    CompanyConfig(
        name="Brex",
        url="https://boards-api.greenhouse.io/v1/boards/brex/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="ByteDance",
        url=(
            "https://jobs.bytedance.com/api/v1/search/job/posts"
            "?keyword=intern&portal_type=2"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # ATSX CSRF POST API (joinbytedance.com careers search)
    ),
    CompanyConfig(
        name="Instacart",
        url="https://boards-api.greenhouse.io/v1/boards/instacart/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Aurora",
        url="https://boards-api.greenhouse.io/v1/boards/aurorainnovation/jobs?content=true",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Mobileye",
        url="https://api.eu.lever.co/v0/postings/mobileye",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Lever EU API; US api.lever.co 404; commitment filter returns []
    ),
    CompanyConfig(
        name="Applied Intuition",
        url="https://api.ashbyhq.com/posting-api/job-board/applied",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Plaid",
        url="https://api.ashbyhq.com/posting-api/job-board/plaid",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Ramp",
        url="https://api.ashbyhq.com/posting-api/job-board/ramp",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    # REMOVED — NASA: STEM Gateway blocks automated requests
    CompanyConfig(
        name="JPL",
        url="https://www.jpl.nasa.gov/careers/internships/",
        level_keywords=STRICT_INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=False,  # NASA site blocks automated fetches (403)
    ),
    CompanyConfig(
        name="John Deere",
        url=(
            "https://careers.deere.com/api/pcsx/search"
            "?domain=johndeere.com&query=intern"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # Eightfold PCSX search API (careers.deere.com SPA front-end)
    ),
    CompanyConfig(
        name="Palantir",
        url="https://api.lever.co/v0/postings/palantir?commitment=Internship",
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Tesla",
        url="https://www.tesla.com/careers/search/?type=3&query=intern",
        level_keywords=STRICT_INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=False,  # Akamai Bot Manager blocks datacenter fetches (403/429/challenge)
    ),
    CompanyConfig(
        name="TikTok",
        url=(
            "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
            "?keywords=intern"
        ),
        level_keywords=INTERN_LEVEL_KEYWORDS,
        cycle_keywords=INTERN_CYCLE_KEYWORDS,
        enabled=True,  # ATSX supplier POST API (lifeattiktok.com careers search)
    ),
]
