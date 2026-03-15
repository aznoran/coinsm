# Browser Automation — coins.bank.gov.ua

Automates clicking the "Купити" button on coins.bank.gov.ua product pages within scheduled time windows. Uses your real Chrome profile (cookies/auth), so you must be logged in to the site in Chrome beforehand.

## Requirements

- macOS
- Python 3.9+
- Google Chrome installed at `/Applications/Google Chrome.app`
- Logged into coins.bank.gov.ua in Chrome

## Setup

```bash
cd evgencoins

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install Playwright's Chromium (needed for CDP connection)
playwright install chromium
```

## Run

```bash
source .venv/bin/activate
python run.py
```

Open **http://localhost:8000** in your browser.

## How it works

1. **Add a page** — paste the product URL from coins.bank.gov.ua, give it a label, pick a date and time window (start/end).
2. **Schedule** — the app schedules the task to start at your specified time (local timezone).
3. **Run Now** — or press the ▶ button to run immediately without waiting for the schedule.
4. **Automation** — when the task runs:
   - Chrome will quit and relaunch with a debug port (your tabs will be restored next time you open Chrome normally)
   - A new tab opens with the product page
   - If the "Купити" button is found, it clicks it
   - If not found, it refreshes every 1–3 seconds until the button appears or the time window expires
5. **Status updates** — the UI updates in real-time via SSE: `pending` → `scheduled` → `in-progress` → `pressed` / `expired` / `failed`

## Important notes

- **Chrome will be restarted** when a task runs. Save your work in Chrome before the scheduled time. Chrome needs to relaunch with a debug port — this is a Chrome requirement, not a limitation of the app.
- **You must be logged in** to coins.bank.gov.ua in Chrome before running. The app copies your cookies from Chrome's profile to authenticate.
- **One task at a time** — if multiple pages have overlapping windows, they run sequentially.
- **Times are local** — enter times in your local timezone, no UTC conversion needed.

## Test page

A mock test page is included at `http://localhost:8000/static/test_target.html`.

- `?delay=5` — button appears after 5 seconds (simulates "not ready yet" scenario)

## Project structure

```
├── run.py              # Entry point (uvicorn)
├── requirements.txt
├── app/
│   ├── config.py       # Chrome profile path, DB path, host/port
│   ├── database.py     # SQLite schema + queries
│   ├── schemas.py      # Pydantic models
│   ├── api.py          # REST + SSE endpoints
│   ├── scheduler.py    # APScheduler job management
│   └── automation.py   # Chrome launch + Playwright click loop
├── static/
│   ├── index.html      # UI
│   ├── style.css
│   ├── app.js
│   └── test_target.html
└── data/               # SQLite DB (created at runtime)
```
