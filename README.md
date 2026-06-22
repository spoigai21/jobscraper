# Internship Monitor

A Python daemon that polls 20+ company career pages for new internship postings and alerts you when relevant roles appear. It tracks individual job listings, scores them against your profile, and sends push + email on every match — with SMS and voice calls for high-priority roles.

## Prerequisites

- **Python 3.11+**
- **[Twilio](https://www.twilio.com/)** account (free trial works for testing)
- **Gmail app password** (not your regular Gmail password)
- **[Ntfy](https://ntfy.sh/)** app installed on your phone (iOS or Android)

## Setup

### 1. Clone and install dependencies

```bash
git clone <your-repo-url>
cd joblistingdetector
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in every value. See the sections below for where to get each credential.

### 3. Twilio setup

1. Sign up for a free trial at [twilio.com/try-twilio](https://www.twilio.com/try-twilio).
2. Open the [Twilio Console](https://console.twilio.com/).
3. Copy your **Account SID** and **Auth Token** from the dashboard into `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`.
4. Buy or claim a trial phone number under **Phone Numbers → Manage → Buy a number**.
5. Set `TWILIO_FROM_NUMBER` to your Twilio number (E.164 format, e.g. `+15551234567`).
6. Set `TWILIO_TO_NUMBER` to your personal cell number (must be verified on trial accounts).
7. Under **Verified Caller IDs**, add your personal number if using a trial account.

### 4. Gmail app password

Gmail requires a 16-character app password for SMTP access (your normal password will not work).

1. Enable 2-Step Verification on your Google account: [Google Account Security](https://myaccount.google.com/security).
2. Create an app password: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (or see [Google's help article](https://support.google.com/accounts/answer/185833)).
3. Choose **Mail** and your device, then copy the generated password.
4. Set `GMAIL_ADDRESS` to your Gmail address, `GMAIL_APP_PASSWORD` to the app password, and `ALERT_EMAIL_TO` to the address that should receive alerts (can be the same Gmail).

### 5. Ntfy push notifications

[Ntfy](https://ntfy.sh/) sends free push notifications to your phone without an account.

1. Install the app:
   - **iOS:** [App Store](https://apps.apple.com/app/ntfy/id1625396347)
   - **Android:** [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. Pick a unique, hard-to-guess topic name (e.g. `savir-intern-alerts-x7k2m9`). Anyone who knows the topic can send to it, so treat it like a secret.
3. In the Ntfy app, subscribe to that topic (tap **+** → enter topic name).
4. Set `NTFY_TOPIC` in `.env` to the same topic string.

### 6. Test alerts before running

Verify notification channels work:

```bash
python cli.py test-alerts
```

This sends a **high-tier** test through all channels (push, email, SMS, call). Standard alerts use push + email only.

You should see a green checkmark for each configured channel. Fix any red ✗ before proceeding.

### 7. Run locally

Start the monitor daemon:

```bash
python main.py
```

The monitor runs an immediate poll on startup, then re-polls every **45 minutes** during business hours (9 AM–7 PM Eastern) and every **3 hours** outside that window. Press `Ctrl+C` to stop.

**Useful CLI commands:**

| Command | Description |
|---------|-------------|
| `python cli.py status` | Dashboard of all monitored companies |
| `python cli.py alerts` | Recent alert history with channel status |
| `python cli.py toggle "Google"` | Enable/disable a company |
| `python cli.py run` | Same as `python main.py` |

## Project layout

```
joblistingdetector/
├── main.py              # Daemon entry point (used by Railway)
├── cli.py               # CLI entry point
├── monitor/             # Application package
│   ├── app.py           # Polling loop and scheduler
│   ├── alerts.py        # Push, email, SMS, voice delivery
│   ├── companies.py     # Monitored company list
│   ├── config.py        # Settings from .env
│   ├── models.py        # Shared dataclasses
│   ├── profile.py       # profile.yaml loader
│   ├── profile.yaml     # Your skills, filters, alert tiers
│   ├── scoring.py       # Job relevance scoring
│   ├── scraper.py       # Careers page fetching and diffing
│   ├── storage.py       # SQLite state + alert log
│   ├── cli.py           # Click commands
│   └── parsers/
│       ├── boards.py    # Greenhouse, Ashby, Lever, Uber APIs
│       └── nasa.py      # NASA STEM Gateway scraper
├── tests/
├── railway.toml         # Railway deploy config
└── Procfile             # Process definition for Railway/Heroku
```

Runtime files (`monitor.db`, `monitor.log`) are written to the project root.

## Deploy to Railway

[Railway](https://railway.com/) runs the monitor 24/7 on their free tier so you do not need to keep your laptop open.

### 1. Install the Railway CLI

```bash
# macOS (Homebrew)
brew install railway

# npm (all platforms)
npm i -g @railway/cli

# Or see: https://docs.railway.com/develop/cli
```

### 2. Log in and initialize

```bash
railway login
cd joblistingdetector
railway init
```

Choose **Empty Project** or link to an existing one.

### 3. Set environment variables

Set every variable from `.env.example` (never commit `.env`):

```bash
railway variables set TWILIO_ACCOUNT_SID=ACxxxxxxxx
railway variables set TWILIO_AUTH_TOKEN=your_token
railway variables set TWILIO_FROM_NUMBER=+15551234567
railway variables set TWILIO_TO_NUMBER=+15559876543
railway variables set NTFY_TOPIC=your-secret-topic
railway variables set GMAIL_ADDRESS=you@gmail.com
railway variables set GMAIL_APP_PASSWORD=your_app_password
railway variables set ALERT_EMAIL_TO=you@gmail.com
```

Optional tuning variables (`POLL_INTERVAL_BUSINESS`, `POLL_INTERVAL_OVERNIGHT`, etc.) can be set the same way.

### 4. Attach persistent storage (recommended)

By default Railway uses an ephemeral filesystem — `monitor.db` is reset on every redeploy, which re-seeds all companies and can miss listings that appeared during downtime.

**Dashboard:** Volumes are not under Service Settings. In your project canvas, press **Cmd+K** (Mac) or **Ctrl+K** (Windows/Linux), search **New Volume**, and attach it to your worker service with mount path `/data`. You can also right-click empty canvas space to create one. See [Railway Volumes docs](https://docs.railway.com/volumes).

**CLI:**

```bash
railway volume add --mount-path /data
```

Then set the database path:

```bash
railway variables set MONITOR_DB_PATH=/data/monitor.db
```

Poll state (`seen_job_ids`, cooldown timestamps) and alert history then survive redeploys. Free tier includes one 0.5 GB volume — plenty for SQLite.

After the first poll, confirm the file exists (Railway service shell or `railway volume browse /`):

```bash
ls -la /data/monitor.db
```

If SQLite writes fail with permission errors, set `RAILWAY_RUN_UID=0`.

### 5. Deploy

```bash
railway up
```

Railway reads `Procfile` and `railway.toml` automatically. The `worker` process runs `python main.py` and restarts on failure (up to 3 retries).

View logs:

```bash
railway logs
```

## Customizing companies

Edit `monitor/companies.py` to add, remove, or tune which career pages are monitored. Each entry is a `CompanyConfig`:

```python
CompanyConfig(
    name="Stripe",
    url="https://stripe.com/jobs/search?query=intern",
    keywords=["intern", "internship", "2027", "summer 2027", "co-op"],
    enabled=True,
),
```

- **name** — Display name used in alerts and the CLI.
- **url** — Direct link to the company's internship search or careers page.
- **keywords** — All must be present logic is *not* used; an alert fires when *any* keyword matches after a page change. Tighten keywords (e.g. add `"summer"`, `"2027"`) to reduce noise.
- **enabled** — Set to `False` to skip a company without deleting it, or run `python cli.py toggle "Stripe"`.

After editing `monitor/companies.py`, restart the monitor (`python main.py` or redeploy on Railway).

## Alert tiers

Channel routing is configured in `monitor/profile.yaml`:

| Tier | Score | Channels |
|------|-------|----------|
| Standard | below 7 | push, email |
| High | 7+ | push, email, SMS, call |

Edit `monitor/profile.yaml` to change thresholds or channels.

## Troubleshooting

### False positives

Career pages change frequently (cookie banners, nav updates, job count widgets). The scraper strips `<nav>`, `<footer>`, `<header>`, `<script>`, and `<style>` tags to reduce noise, but some sites still trigger alerts on non-internship updates.

**Fixes:**

- Add more specific keywords in `monitor/companies.py` (e.g. `"summer 2027"` instead of just `"intern"`).
- Increase `MIN_ALERT_INTERVAL` in `.env` (default `3600` = 1 hour) so the same company cannot re-alert too quickly.
- Disable noisy companies with `python cli.py toggle "Company Name"`.

Profile-based filters in `monitor/profile.yaml` (`roles_exclude`, `location`) also drop irrelevant postings on per-job boards (Greenhouse, Ashby, Lever, Uber).

### Rate limiting

Aggressive polling can get your IP blocked by career sites.

**Fixes:**

- Do not lower `POLL_INTERVAL_BUSINESS` below `2700` (45 minutes) without good reason.
- Increase `POLL_INTERVAL_OVERNIGHT` if you see HTTP 429 or timeout warnings in `monitor.log`.
- If one company consistently fails, set `enabled=False` for that entry.

### Twilio trial limits

Twilio trial accounts have restrictions that affect this project:

- **Verified numbers only** — SMS and voice calls can only reach phone numbers you verified in the [Twilio Console](https://console.twilio.com/us1/develop/phone-numbers/manage/verified). Add your cell under **Phone Numbers → Verified Caller IDs**.
- **Trial message prefix** — Outbound SMS include a "Sent from your Twilio trial account" prefix.
- **Limited balance** — Trial credit is finite. Voice calls use more credit than SMS.
- **US/Canada numbers** — Trial numbers are typically US-only; international delivery may not work.

Upgrade to a paid Twilio account when you are ready to deploy long-term.

### Other issues

| Symptom | Likely cause |
|---------|----------------|
| No email alerts | Wrong app password, or 2FA not enabled on Gmail |
| No push notifications | Topic mismatch between `.env` and Ntfy app subscription |
| `monitor.db` errors on Railway | Missing volume — set `MONITOR_DB_PATH` to a mounted volume path (see Deploy section) |
| Import errors | Run `pip install -r requirements.txt` inside your virtualenv |

Check `monitor.log` in the project root for detailed error messages.

## Testing

Run the scraper unit tests with pytest:

```bash
pytest tests/
```
