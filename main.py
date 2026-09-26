"""LeadScout AI - find local businesses that need your services.

Pipeline:
    1. Parse the plain-language request       (modules.nlp_parser)
    2. Collect leads per category             (modules.osm_collector, modules.maps_collector)
    3. Merge and remove duplicates            (modules.merge)
    4. Enrich with social media and email     (modules.enrichment)
    5. Filter and score                       (modules.filters)
    6. Export to Excel                        (modules.excel_export)

Usage:
    python main.py                              Interactive: asks what you're looking for
    python main.py --request "salons in Karachi that need a website"
    python main.py --request "..." --dry-run    Show what would be searched, collect nothing
    python main.py --check                      Verify this machine is ready

Developer tests (see dev_tests.py):
    --test-osm, --test-maps, --test-merge, --test-enrich, --test-filter,
    --test-export, --test-parser

Every run writes a log file to config.LOG_DIR. When a step fails, the error
details go there and the pipeline continues with what it has.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import config

log = logging.getLogger("leadscout")

EXAMPLES = [
    "restaurants in Lahore that need a website",
    "salons in Karachi without social media",
    "gyms in Islamabad that need a website and have a phone number",
    "businesses in Lahore that need a website   (searches all categories)",
]


# --- Logging -----------------------------------------------------------------

def setup_logging() -> Path | None:
    """Log everything to a daily file (progress is printed by the pipeline callback)."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = config.LOG_DIR / f"leadscout_{datetime.now():%Y-%m-%d}.log"
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(file_handler)
    except OSError as exc:
        print(f"(Could not create log file in {config.LOG_DIR}: {exc})")
        return None
    # Quiet noisy third-party libraries in the log file.
    for noisy in ("urllib3", "asyncio", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return path


# --- Pipeline ----------------------------------------------------------------

def _elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _estimate_minutes(n_categories: int, maps_max: int) -> int:
    # Roughly: ~10s OpenStreetMap + ~4s per Google Maps listing + website checks.
    per_category = 10 + maps_max * 4 + maps_max * 2
    return max(1, round(n_categories * per_category / 60))


def _print_plan(parsed: dict) -> None:
    categories = parsed["categories"]
    shown = ", ".join(categories) if len(categories) <= 4 else \
        f"all {len(categories)} common types ({', '.join(categories[:4])}, ...)"
    filters = ", ".join(r if isinstance(r, str) else f"{r[0]} < {r[1]}" for r in parsed["filters"])
    print(f"  Business type : {shown}")
    print(f"  Location      : {parsed['location'] or '(not found)'}")
    print(f"  Looking for   : {filters or 'all businesses (no filter)'}")


def _ask(prompt: str) -> str | None:
    """input() that returns None instead of crashing when input is closed."""
    try:
        return input(prompt).strip()
    except EOFError:
        return None


_STAGE_HEADINGS = {"collect": "[2/5]", "enrich": "[3/5]", "score": "[4/5]", "export": "[5/5]"}


def _print_progress(stage: str, message: str, fraction: float | None) -> None:
    """Command-line display for modules.pipeline progress events."""
    if stage in _STAGE_HEADINGS:
        extra = " (Ctrl+C to stop early and keep what's found)" if stage == "collect" else ""
        print(f"\n{_STAGE_HEADINGS[stage]} {message}{extra}")
    elif stage in ("osm", "maps", "merge"):
        print(f"    {message}")
    elif stage == "detail":
        print(f"      {message}")
    elif stage == "warning":
        print(f"    ! {message}\n      (continuing; details in the log file)")


def run_request(text: str, interactive: bool = False):
    """Parse a request, confirm if needed, and run the pipeline. Returns a PipelineResult or None."""
    from modules.nlp_parser import parse_user_request
    from modules.pipeline import run_pipeline

    log.info("=== New request: %r", text)
    print("\n[1/5] Understanding your request...")
    try:
        parsed = parse_user_request(text)
    except Exception:  # noqa: BLE001
        log.exception("Parsing failed")
        print('  Sorry, I couldn\'t understand that request. Try e.g. "salons in Karachi".')
        return None
    if not parsed["location"] and interactive:
        parsed["location"] = _ask("  Which city or area should I search? ") or None
    _print_plan(parsed)
    if not parsed["location"]:
        print('\n  No location found. Include one, e.g. "salons in Karachi".')
        return None

    if interactive and len(parsed["categories"]) > 2:
        minutes = _estimate_minutes(len(parsed["categories"]), config.ALL_CATEGORIES_MAPS_MAX)
        answer = _ask(f"\n  This searches {len(parsed['categories'])} business types and may take "
                      f"about {minutes} minutes. Continue? [Y/n] ")
        if answer is None or answer.lower().startswith("n"):
            print("  Cancelled.")
            return None

    result = run_pipeline(parsed, on_progress=_print_progress)
    if not result.leads:
        print("\n  No businesses were found. Try a different area or business type.")
    return result


def print_summary(text: str, result, log_path: Path | None) -> None:
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Request          : {text}")
    print(f"  Businesses found : {len(result.leads)}  (OpenStreetMap {result.osm_count}, "
          f"Google Maps {result.maps_count}, after removing duplicates)")
    matched = len(result.matched) if result.filters_applied else "n/a (filters could not be applied)"
    print(f"  Matched filters  : {matched}")
    print(f"  Saved to         : {result.output_path or '(nothing saved)'}")
    print(f"  Time taken       : {_elapsed(result.seconds)}")
    if result.stopped_early:
        print("  Note             : stopped early by you; results are partial")
    if result.errors:
        print(f"  Problems         : {len(result.errors)} step(s) failed, the rest completed:")
        for error in result.errors[:5]:
            print(f"                     - {error[:90]}")
        if log_path:
            print(f"                     Details: {log_path}")
    else:
        print("  Problems         : none")
    print("=" * 60)


# --- Entry points ------------------------------------------------------------

def interactive_mode(log_path: Path | None) -> int:
    print("=" * 60)
    print("  LeadScout AI - find businesses that need your services")
    print("=" * 60)
    print("Describe the leads you want in plain language. Examples:")
    for example in EXAMPLES:
        print(f"  - {example}")
    print("Type 'q' to quit.")

    while True:
        text = _ask("\nWhat leads are you looking for? > ")
        if text is None or text.lower() in ("q", "quit", "exit"):
            print("Goodbye!")
            return 0
        if not text:
            continue
        result = run_request(text, interactive=True)
        if result is not None:
            print_summary(text, result, log_path)


def check_environment() -> bool:
    """Check dependencies, browser, output folder and network. Returns True if all pass."""
    ok = True

    def report(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"  [{'OK' if passed else 'FAIL'}] {name}{f' - {detail}' if detail else ''}")

    print("LeadScout AI - environment check\n")

    try:
        import bs4, openpyxl, overpy, pandas, playwright, rapidfuzz, requests  # noqa: F401,E401
        report("Python libraries", True)
    except ImportError as exc:
        report("Python libraries", False, str(exc))

    for label, folder in (("Output folder writable", config.OUTPUT_DIR),
                          ("Log folder writable", config.LOG_DIR)):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".write_test"
            probe.write_text("ok")
            probe.unlink()
            report(label, True, str(folder))
        except OSError as exc:
            report(label, False, f"{folder} ({exc})")

    try:
        from playwright.sync_api import sync_playwright

        from modules.browser import BROWSER_NAMES, launch_browser

        with sync_playwright() as p:
            browser, channel = launch_browser(p, headless=True)
            version = browser.version
            browser.close()
        report("Browser", True, f"{BROWSER_NAMES.get(channel, channel)} {version}")
    except Exception as exc:  # noqa: BLE001
        report("Browser", False, str(exc))

    try:
        import requests

        requests.get(config.OVERPASS_URL.rsplit("/", 1)[0] + "/status",
                     timeout=config.REQUEST_TIMEOUT)
        report("Internet (OpenStreetMap)", True)
    except Exception as exc:  # noqa: BLE001
        report("Internet (OpenStreetMap)", False, type(exc).__name__)

    print("\nAll checks passed." if ok else "\nSome checks failed.")
    return ok


def main() -> int:
    # Business names can be non-Latin (e.g. Urdu); avoid crashes on Windows consoles.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="LeadScout", description="LeadScout AI")
    parser.add_argument("--request", metavar="TEXT",
                        help='run once for a request, e.g. "salons in Karachi that need a website"')
    parser.add_argument("--dry-run", action="store_true",
                        help="with --request: only show what would be searched")
    parser.add_argument("--check", action="store_true",
                        help="verify this machine is ready to run LeadScout AI")
    dev = parser.add_argument_group("developer tests")
    for name in ("osm", "maps", "merge", "enrich", "filter", "export", "parser"):
        dev.add_argument(f"--test-{name}", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.check:
        return 0 if check_environment() else 1

    for name in ("osm", "maps", "merge", "enrich", "filter", "export", "parser"):
        if getattr(args, f"test_{name}"):
            import dev_tests
            return getattr(dev_tests, f"test_{name}")()

    if args.request is not None and args.dry_run:
        from modules.nlp_parser import parse_user_request
        print(f"Request: {args.request}")
        _print_plan(parse_user_request(args.request))
        print("\nDry run: nothing collected.")
        return 0

    log_path = setup_logging()
    if args.request is not None:
        result = run_request(args.request)
        if result is None:
            return 1
        print_summary(args.request, result, log_path)
        return 0 if result.output_path else 1
    return interactive_mode(log_path)


if __name__ == "__main__":
    try:
        exit_code = main()
    except KeyboardInterrupt:
        print("\nStopped.")
        exit_code = 130
    except Exception:  # noqa: BLE001 - last resort: never vanish without a message
        logging.getLogger("leadscout").exception("Unexpected crash")
        import traceback
        traceback.print_exc()
        print("\nLeadScout AI hit an unexpected error (details above and in the log folder).")
        exit_code = 1
        if getattr(sys, "frozen", False):  # keep a double-clicked window open
            input("\nPress Enter to close...")
    sys.exit(exit_code)
