from __future__ import annotations

from models import CompanyConfig

DEFAULT_KEYWORDS: list[str] = ["intern", "internship", "2027", "2026"]

COMPANIES: list[CompanyConfig] = [
    CompanyConfig(name="Google", url="https://careers.google.com/jobs/results/?employment_type=INTERN", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Meta", url="https://www.metacareers.com/jobs?roles[0]=intern", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Amazon", url="https://www.amazon.jobs/en/search?base_query=intern", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Apple", url="https://jobs.apple.com/en-us/search?search=intern&sort=newest", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Uber", url="https://www.uber.com/us/en/careers/list/?query=intern", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Waymo", url="https://waymo.com/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Skydio", url="https://www.skydio.com/jobs", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Zoox", url="https://zoox.com/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Cruise", url="https://getcruise.com/careers/jobs/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Luminar", url="https://www.luminartech.com/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Matterport", url="https://matterport.com/careers", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="SpaceX", url="https://www.spacex.com/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Rocket Lab", url="https://www.rocketlabusa.com/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Blue Origin", url="https://www.blueorigin.com/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Planet Labs", url="https://www.planet.com/company/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Relativity", url="https://www.relativityspace.com/careers", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Firefly", url="https://fireflyspace.com/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Muon Space", url="https://www.muonspace.com/careers", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Astranis", url="https://www.astranis.com/careers", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Air Space Intelligence", url="https://airspace-intelligence.com/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Scale AI", url="https://scale.com/careers", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="NVIDIA", url="https://www.nvidia.com/en-us/about-nvidia/careers/", keywords=DEFAULT_KEYWORDS, enabled=True),
    CompanyConfig(name="Nuro", url="https://www.nuro.ai/careers", keywords=DEFAULT_KEYWORDS, enabled=True),
]
