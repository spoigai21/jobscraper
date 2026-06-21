"""Company careers pages to monitor for internship listings."""

from __future__ import annotations

from models import CompanyConfig

DEFAULT_KEYWORDS: list[str] = ["intern", "internship", "2027", "2026"]

# Pre-filtered internship job boards: seasonal phrases reduce footer/copyright noise.
FILTERED_INTERN_KEYWORDS: list[str] = [
    "intern",
    "internship",
    "summer 2027",
    "summer 2026",
    "fall 2027",
    "fall 2026",
]

# Generic career homepages: avoid bare "intern" (matches "internal") and bare years.
STRICT_INTERN_KEYWORDS: list[str] = [
    "internship",
    "summer intern",
    "engineering intern",
    "software intern",
    "summer 2027",
    "summer 2026",
    "fall 2027",
    "fall 2026",
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
        url="https://www.metacareers.com/jobs?roles[0]=intern",
        keywords=DEFAULT_KEYWORDS,
        enabled=True,
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
        keywords=DEFAULT_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Uber",
        url="https://www.uber.com/us/en/careers/list/?query=intern",
        keywords=DEFAULT_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Waymo",
        url="https://careers.withwaymo.com/jobs/search?employment_type=Intern",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Skydio",
        url="https://jobs.ashbyhq.com/skydio?department=Intern",
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
        url="https://www.spacex.com/internships",
        keywords=[
            "intern program",
            "internship/co-op",
            "engineering intern",
            "software intern",
            "summer 2027",
            "summer 2026",
        ],
        enabled=True,
    ),
    CompanyConfig(
        name="Rocket Lab",
        url="https://job-boards.greenhouse.io/rocketlab?keyword=intern",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Blue Origin",
        url="https://blueorigin.wd5.myworkdayjobs.com/BlueOrigin?q=intern",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Planet Labs",
        url="https://www.planet.com/company/careers/?depId=internships",
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
            "summer 2026",
            "accepting applications",
        ],
        enabled=True,
    ),
    CompanyConfig(
        name="Firefly",
        url="https://fireflyspace.com/careers/",
        keywords=STRICT_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Muon Space",
        url="https://job-boards.greenhouse.io/muonspace?keyword=intern",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Astranis",
        url="https://job-boards.greenhouse.io/astranis?keyword=intern",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Air Space Intelligence",
        url="https://www.airspace-intelligence.com/careers",
        keywords=STRICT_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="Scale AI",
        url="https://scale.com/careers/university",
        keywords=FILTERED_INTERN_KEYWORDS,
        enabled=True,
    ),
    CompanyConfig(
        name="NVIDIA",
        url="https://jobs.nvidia.com/careers?filter_job_type=intern+%28fixed+term%29",
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
            "summer 2026",
        ],
        enabled=True,
    ),
]
