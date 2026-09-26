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

3. **Run the app:**

   ```bash
   streamlit run app.py
   ```

   Your browser opens at http://localhost:8501. Type a request such as
   *"restaurants in Lahore that need a website"* and click **Find Leads**.
   A search takes about 2-4 minutes per business type; progress is shown live.
   When it finishes you get summary metrics, a searchable results table, and a
   **Download Excel File** button. Previous searches stay in the sidebar until
   you close the tab.

The app is only reachable from this computer (`.streamlit/config.toml` binds it
to `localhost`). Excel files are also saved in `output/`, and error details in
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
├── Dockerfile           # Optional Docker deployment
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

## Deployment with Docker (optional)

For machines that already have Docker. The image is based on the official
Playwright image, which includes Chromium.

```bash
docker compose run --rm leadscout --check
docker compose run --rm leadscout
```

Excel files appear in `./output` on the host.

## Responsible use

Respect each data source's terms of service and rate limits. OpenStreetMap
data is licensed under the ODbL and requires attribution. Automated access to
Google Maps may conflict with Google's terms, so review them before use.
