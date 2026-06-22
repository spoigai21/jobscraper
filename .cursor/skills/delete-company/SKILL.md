---
name: delete-company
description: >-
  Remove a company from the internship monitor entirely. Use when the user asks
  to delete, remove, drop, or stop tracking a company from the monitor (not just
  disable it).
---

# Delete Company

Remove a company from monitoring config, prestige scoring, tests, and docs.

**Disable vs delete:** `python cli.py toggle "Company Name"` flips `enabled` in `companies.py` without removing the entry. This skill is for **full removal**.

## Trigger phrases

- delete company / remove company / drop company
- stop monitoring [Company] entirely
- remove [Company] from the monitor / from companies.py

## Checklist

Copy and track progress:

```
- [ ] 1. Grep for all references (name + slug variants)
- [ ] 2. Remove CompanyConfig from monitor/companies.py
- [ ] 3. Remove from monitor/profile.yaml prestige tiers (if present)
- [ ] 4. Remove or update tests that hardcode the company name
- [ ] 5. Remove from README.md if mentioned by name
- [ ] 6. Re-grep — zero meaningful refs remain
- [ ] 7. Run pytest
- [ ] 8. Do NOT commit unless user asks
```

## Step 1: Find all references

Replace `COMPANY` with display name (e.g. `Anduril`, `Cruise`) and `SLUG` with board/API slug (e.g. `andurilindustries`, `getcruise`).

```bash
# Display name (case insensitive)
rg -i 'COMPANY' --glob '!*.db' --glob '!.git/**'

# Greenhouse board slug (often differs from display name)
rg -i 'SLUG' --glob '!*.db'

# Exact name= in companies.py
rg 'name="COMPANY"' monitor/

# Prestige tiers
rg -i 'COMPANY' monitor/profile.yaml
```

**Known locations in this repo:**

| File | What to check |
|------|---------------|
| `monitor/companies.py` | `CompanyConfig(name="...", ...)` block in `COMPANIES` |
| `monitor/profile.yaml` | `prestige.tier_s/a/b/c` lists (names must match `CompanyConfig.name` exactly) |
| `tests/test_companies.py` | `_company("Name")` assertions (Relativity, Meta, Zoox today) |
| `tests/test_scoring.py` | `company_name="..."` in scoring fixtures |
| `tests/test_*_scraper.py` | `is_*_company("Name")` helpers (Meta, NASA, Tesla) |
| `README.md` | Only if company named explicitly (usually generic Stripe example) |

**Not company-specific (no edit needed):**

- `monitor/app.py`, `monitor/cli.py` — iterate `COMPANIES` dynamically
- `monitor/scraper.py`, `monitor/parsers/boards.py` — board-type parsers, no company list
- `.env.example` — no per-company config

**Orphan prestige entries:** `tier_c` lists Snap, Adobe, ByteDance, TikTok with no `CompanyConfig` — prestige-only placeholders. Remove from tiers only when deleting a company that was listed there.

## Step 2: Remove from companies.py

Delete the entire `CompanyConfig(...)` block including trailing comma. Preserve list formatting.

Reference removal (Cruise, Anduril):

```python
# REMOVED — Cruise: HTML careers page, enabled=False
# REMOVED — Anduril: Greenhouse boards-api.greenhouse.io/v1/boards/andurilindustries/jobs?content=true
```

## Step 3: Remove from profile.yaml

Under `prestige:`, delete the company from whichever tier list it appears in:

```yaml
prestige:
  tier_s: [Google, Meta, ...]
  tier_a: [Stripe, SpaceX, ...]
  tier_b: [Zoox, Skydio, ...]
  tier_c: [Ramp, DoorDash, ...]
```

Names are case-sensitive and must match `CompanyConfig.name` (e.g. `SpaceX`, not `Spacex`).

## Step 4: Update tests

- `tests/test_companies.py` — remove test class if it only covered this company
- Other test files — only edit if they reference the deleted company by name from `COMPANIES` (most use ad-hoc `CompanyConfig` fixtures like `TestCo`, `Waymo`)

## Step 5: Docs

`README.md` describes the generic `CompanyConfig` shape; edit only if the company appears by name.

## Step 6: Verify zero refs

```bash
rg -i 'COMPANY|SLUG' --glob '!*.db' --glob '!.git/**'
# Expect no hits (or only this skill / git history)
```

## Step 7: Run tests

```bash
pytest
# Or targeted:
pytest tests/test_companies.py tests/test_profile.py
```

## Orphan DB rows

SQLite state (`MONITOR_DB_PATH`, default `monitor.db`) may retain rows for the deleted company (`company` column in poll state / alert history). **Harmless** — the monitor no longer polls removed companies. No migration required unless the user explicitly asks to purge history.

## Do not commit

Do not `git commit` or open a PR unless the user explicitly requests it.
