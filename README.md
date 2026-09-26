---
title: LeadScout AI
emoji: 🔎
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Find local businesses that need a website or social media
---

# LeadScout AI

A free, local lead-generation tool. LeadScout AI collects business leads
(restaurants, salons, clinics, etc.) from OpenStreetMap and Google Maps,
enriches them with website and social media data, filters them by missing
information (e.g. "needs a website"), and exports the results to a clean
Excel file.

It uses only free, open-source Python libraries. No paid APIs.

## Getting Started

**Requirements:** Windows 10/11 (or macOS/Linux), Python 3.11+, an internet
connection, and Google Chrome or Microsoft Edge (Edge comes with Windows).

1. **Install the requirements** (once):

   ```bash
   cd leadscout
   python -m venv .venv
   .venv\Scriptsctivate            # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Browser for Google Maps (Phase 2)** - usually nothing to do. LeadScout drives
   the Chrome or Edge already installed on the PC (Chrome first, then Edge). Only
   if the PC has neither, download Playwright's own browser:

   ```bash
   playwright install chromium
   ```

   and set `LEADSCOUT_BROWSER_CHANNELS=bundled`. Run `python main.py --check` to
   confirm which browser will be used.

3. **Run the app:** double-click `run_app.bat`, or run:

   ```bash
   streamlit run app.py --server.address localhost
   ```

   Your browser opens at http://localhost:8501. Type a request such as
   *"restaurants in Lahore that need a website"* and click **Find Leads**.
   A search takes about 2-4 minutes per business type; progress is shown live.
   When it finishes you get summary metrics, a searchable results table, and a
   **Download Excel File** button. Previous searches stay in the sidebar until
   you close the tab.

`--server.address localhost` (used by `run_app.bat`) keeps the app reachable
only from this computer. In addition, without a password the app refuses
visitors from other devices. Excel files are also saved in `output/`, and error details in
`logs/`.

## Project structure

```
leadscout/
├── app.py               # Web interface (streamlit run app.py)
├── main.py              # Command-line interface + environment check
├── config.py            # Settings: rate limits, categories, folders, browsers
├── dev_tests.py         # Developer test commands (main.py --test-*)
├── modules/
│   ├── pipeline.py      # The full pipeline, shared by app.py and main.py
│   ├── nlp_parser.py    # Plain-language request -> category/location/filters
│   ├── osm_collector.py # OpenStreetMap (Nominatim + Overpass API)
│   ├── maps_collector.py# Google Maps (Playwright; light use only)
│   ├── merge.py         # Merge sources, remove duplicates, normalize
│   ├── enrichment.py    # Social media links + email from websites
│   ├── filters.py       # Filter rules + lead scoring
│   ├── excel_export.py  # Formatted Excel export
│   ├── lead.py          # Shared lead record format
│   └── browser.py       # Chrome -> Edge browser selection
├── .streamlit/          # Web app settings (local-only, no telemetry)
├── output/              # Generated Excel files
├── logs/                # Daily log files
├── requirements.txt     # Pinned runtime dependencies
├── requirements-dev.txt # + PyInstaller (for building the .exe)
├── build.bat            # Builds the portable Windows command-line app
├── Dockerfile           # Web app container (Hugging Face Spaces / Docker)
├── .github/workflows/   # Auto-deploy to Hugging Face on push
└── README.md
```

## Command line

The same pipeline is also available without the web interface:

```bash
python main.py                                   # interactive: describe the leads you want
python main.py --request "salons in Karachi that need a website"   # one-off run
python main.py --request "..." --dry-run         # show what would be searched
python main.py --check                           # verify libraries, browser, folders, internet
```

Describe what you want in plain language, e.g. *"restaurants in Lahore that need a
website"* or *"businesses in Islamabad without social media"* (no business type =
all types in `DEFAULT_CATEGORIES`). The run goes through five stages with progress
shown on screen: understand the request → collect (OpenStreetMap + Google Maps) →
enrich (social media, email) → filter and score → save to Excel in `output/`.

- **Ctrl+C** stops collection early and still saves what was found.
- If a step fails (e.g. Google Maps doesn't load), the run continues and the
  summary lists what went wrong. Full details are in `logs/leadscout_<date>.log`.
- If the Excel file can't be written, the results are saved as `.json` instead.

Developer tests for each stage: `--test-osm`, `--test-maps`, `--test-merge`,
`--test-enrich`, `--test-filter`, `--test-export`, `--test-parser` (see `dev_tests.py`).

## Deployment to a client PC (Windows)

> The `.exe` built below contains the **command-line** version only; the web
> interface (`app.py`) needs Python on the client PC (see Getting Started).

The client PC does **not** need Python, Docker, or a browser download.

1. On the developer PC, run `build.bat`. It creates `dist\LeadScout\`
   (~170 MB) containing `LeadScout.exe` and everything it needs.
2. Copy the whole `dist\LeadScout` folder to the client PC (zip, USB, etc.).
   Put it somewhere writable, e.g. `C:\LeadScout` or the Desktop, and not
   `C:\Program Files`.
3. On the client PC, double-click `Check Setup.bat`. All checks should pass.
4. Run `LeadScout.exe`. Excel files are saved to the `output` folder beside it.

Requirements on the client: Windows 10/11 (64-bit), an internet connection, and
Google Chrome or Microsoft Edge (Edge is preinstalled, so this is always met).
`Check Setup.bat` shows which browser will be used.

Windows SmartScreen or antivirus may warn about an unsigned `.exe` the first
time. Choose "More info" → "Run anyway", or code-sign the exe for production.

### Settings via environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `LEADSCOUT_OUTPUT_DIR` | `output` next to the app | Where Excel files are saved |
| `LEADSCOUT_BROWSER_CHANNELS` | `chrome,msedge` on Windows, `bundled` elsewhere | Browsers to try, in order: `chrome`, `msedge`, `bundled` |
| `LEADSCOUT_HEADLESS` | `1` | `0` shows the browser window |
| `LEADSCOUT_LOG_DIR` | `logs` next to the app | Where daily log files are written |
| `LEADSCOUT_PHONE_COUNTRY_CODE` | `92` (Pakistan) | Country code for local phone numbers |
| `LEADSCOUT_PASSWORD` | (unset = no login) | Password for the web app. Set it only as a secret, never in code |
| `LEADSCOUT_GOOGLE_MAPS` | `1` | `0` skips Google Maps (OpenStreetMap only) |
| `LEADSCOUT_CONTACT` | this GitHub repo | Contact URL/email sent to OpenStreetMap, as its usage policy requires |

## Online demo on Streamlit Community Cloud (free, recommended)

Streamlit Community Cloud runs the app straight from this GitHub repository.
It has no Chrome/Chromium, so the hosted copy uses **OpenStreetMap + website
enrichment only** (Google Maps switched off).

1. Go to https://share.streamlit.io and sign in with GitHub.
2. *Create app* → *Deploy a public app from GitHub* (or *from a private repo*):
   - Repository: this repo · Branch: `main` · Main file path: `app.py`
   - App URL: pick a name, e.g. `leadscout-ai`
3. *Advanced settings*:
   - Python version: **3.12**
   - Secrets - paste (with your own password between the quotes):

     ```toml
     LEADSCOUT_PASSWORD = "your-password-here"
     LEADSCOUT_GOOGLE_MAPS = "0"
     ```
4. *Deploy*. The first start takes a few minutes. Later pushes to `main`
   update the app automatically.

Visitors see a login page; only people with the password can run searches.
Files are temporary on the server - use *Download Excel File*. Apps sleep after
a period without visitors and take a moment to wake up.

## Online demo on Hugging Face Spaces (paid plan)

Hugging Face now requires a paid (PRO) plan for Docker Spaces. With PRO, this
repository also runs as a Hugging Face **Docker Space**: the header
at the top of this README configures it, and the `Dockerfile` starts the web app
with Playwright's Chromium included. A GitHub Action copies the code to the
Space on every push to `main`.

One-time setup:

1. **Create the Space.** Sign up at https://huggingface.co, then
   *New Space* → name it (e.g. `leadscout-ai`) → SDK **Docker** → template
   **Blank** → hardware **CPU basic (free)** → *Create Space*.
2. **Set the password.** In the Space: *Settings* → *Variables and secrets* →
   *New secret*: name `LEADSCOUT_PASSWORD`, value = the password visitors must
   enter. (Optional: a *variable* `LEADSCOUT_GOOGLE_MAPS` = `0` to skip Google Maps.)
3. **Create an access token.** Hugging Face → *Settings* → *Access Tokens* →
   *Create new token* → type **Write** → copy it.
4. **Connect GitHub.** In this GitHub repository: *Settings* → *Secrets and
   variables* → *Actions*:
   - *Secrets* tab → *New repository secret*: `HF_TOKEN` = the token from step 3.
   - *Variables* tab → *New repository variable*: `HF_SPACE` = `<hf-username>/<space-name>`.
5. **Deploy.** *Actions* tab → *Deploy to Hugging Face Space* → *Run workflow*
   (later pushes to `main` deploy automatically). The first build takes about
   5-10 minutes; then the app is live at
   `https://huggingface.co/spaces/<hf-username>/<space-name>`.

Things to know about the hosted copy:

- **Google Maps is often blocked** from cloud servers (CAPTCHA). The app then
  shows a warning and continues with OpenStreetMap + website enrichment. Run
  locally for complete results.
- **Files are temporary** - use *Download Excel File*; the server's `output/`
  is wiped on restart.
- **Free Spaces sleep** after a period without visitors; the first visit
  afterwards takes a minute or two to wake up.
- Anyone with the link sees the login page; only people with the password can
  run searches. Share the password privately.

## Docker (optional, local)

```bash
docker compose up web                      # web app at http://localhost:8501
docker compose run --rm cli --check        # command-line version
```

Excel files appear in `./output` on the host.

## Responsible use

Respect each data source's terms of service and rate limits. OpenStreetMap
data is licensed under the ODbL and requires attribution. Automated access to
Google Maps may conflict with Google's terms, so review them before use.
