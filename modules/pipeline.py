"""The LeadScout pipeline, independent of any user interface.

    collect (OSM + Google Maps, per category) -> merge -> enrich -> filter/score -> Excel

Used by main.py (command line) and app.py (Streamlit). Progress is reported
through an `on_progress(stage, message, fraction)` callback so each interface
can display it its own way. Every step is isolated: if one fails, the error is
logged and recorded in the result, and the pipeline continues with what it has.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import config
from modules.enrichment import enrich_with_social_and_contact
from modules.excel_export import build_filename, export_to_excel
from modules.filters import filter_leads, score_leads
from modules.merge import merge_and_deduplicate, set_phone_region
from modules.osm_collector import collect_from_osm, resolve_location

log = logging.getLogger(__name__)

# on_progress(stage, message, fraction 0-1 or None)
# stage is one of: "collect", "osm", "maps", "merge", "phones", "enrich", "score", "export",
# "done", "warning", "detail" (item-level lines such as "[3/20] Monal Lahore").
ProgressCallback = Callable[[str, str, float | None], None]


@dataclass
class PipelineResult:
    parsed: dict
    leads: list[dict] = field(default_factory=list)     # all businesses found (scored)
    matched: list[dict] = field(default_factory=list)   # businesses matching the filters
    exported: list[dict] = field(default_factory=list)  # what went into the file (matched, or
                                                        # every lead with a phone if none matched)
    output_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    osm_count: int = 0
    maps_count: int = 0
    filters_applied: bool = True
    phones_looked_up: int = 0      # businesses searched on Google Maps for a phone number
    phones_found: int = 0          # of those, how many got a phone number
    dropped_no_phone: int = 0      # left out because no phone number could be found
    stopped_early: bool = False
    seconds: float = 0.0

    @property
    def average_score(self) -> float | None:
        scores = [b["lead_score"] for b in self.matched if b.get("lead_score") is not None]
        return sum(scores) / len(scores) if scores else None


class _ForwardModuleLogs(logging.Handler):
    """Forward the modules' progress log lines (e.g. "[3/20] Monal") to the callback."""

    def __init__(self, on_progress: ProgressCallback):
        super().__init__(logging.INFO)
        self.on_progress = on_progress

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("modules.") and record.name != __name__ \
                and not getattr(record, "file_only", False):
            try:
                self.on_progress("detail", record.getMessage().strip(), None)
            except Exception:  # noqa: BLE001 - a display problem must never stop the run
                pass


def _load_google_maps():
    """Import the Google Maps collector (Playwright) only when a search needs it.

    On Windows with Smart App Control, loading Playwright's helper library can
    occasionally be blocked for a moment while Windows checks it online. Retrying
    usually works; if not, the search continues without Google Maps instead of
    the whole app failing to start. Returns (module, None) or (None, error text).
    """
    last_error = ""
    for attempt in range(3):
        try:
            from modules import maps_collector
            return maps_collector, None
        except Exception as exc:  # noqa: BLE001 - ImportError / OSError from a blocked DLL
            last_error = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            log.warning("Loading Google Maps support failed (attempt %d): %s", attempt + 1, last_error)
            time.sleep(2)
    return None, last_error


def _save_json(leads: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(leads, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def run_pipeline(parsed: dict, *, osm_max: int | None = None, maps_max: int | None = None,
                 use_google_maps: bool | None = None,
                 on_progress: ProgressCallback | None = None) -> PipelineResult:
    """Run collect -> merge -> enrich -> filter/score -> export for a parsed request.

    parsed: {"category", "categories", "location", "filters"} (see modules.nlp_parser).
    osm_max / maps_max: results per category and source; defaults depend on
    whether one or several categories are searched (see config).
    use_google_maps: False skips Google Maps (default: config.GOOGLE_MAPS_ENABLED).
    Ctrl+C (KeyboardInterrupt) during collection or enrichment stops that stage
    early and the pipeline continues with what was found.
    """
    progress = on_progress or (lambda stage, message, fraction: None)
    result = PipelineResult(parsed=parsed)
    started = time.monotonic()
    categories = parsed["categories"]
    location = parsed["location"]
    many = len(categories) > 1
    osm_max = osm_max or (config.ALL_CATEGORIES_OSM_MAX if many else 100)
    maps_max = maps_max or (config.ALL_CATEGORIES_MAPS_MAX if many else 20)
    if use_google_maps is None:
        use_google_maps = config.GOOGLE_MAPS_ENABLED
    maps_module = None
    if use_google_maps:
        maps_module, maps_error = _load_google_maps()
        if maps_module is None:
            use_google_maps = False
            message = ("Google Maps could not start (Windows blocked a component: "
                       f"{maps_error}). Continuing with OpenStreetMap only - close and restart "
                       "LeadScout AI to try again.")
            result.errors.append(message)
            progress("warning", message, None)
    log.info("Pipeline start: %s (osm_max=%s, maps_max=%s)", parsed, osm_max, maps_max)

    def step(name: str, func, *args, fallback=None, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - a failed step must not end the run
            log.exception("Step failed: %s", name)
            message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            result.errors.append(f"{name}: {message}")
            progress("warning", f"{name} failed: {message[:150]}", None)
            return fallback

    forwarder = _ForwardModuleLogs(progress)
    logging.getLogger().addHandler(forwarder)
    try:
        # 1. Collect (0% - 70%) ------------------------------------------------
        progress("collect", f"Collecting businesses in {location}...", 0.0)

        # Check the place exists (and isn't a whole country) before spending
        # minutes on it, and read phone numbers in that country's format.
        try:
            place = resolve_location(location)
        except ValueError as exc:  # not found, or a whole country/state
            result.errors.append(str(exc))
            progress("warning", str(exc), None)
            return result
        except Exception as exc:  # noqa: BLE001 - e.g. no internet: try anyway
            log.warning("Could not check location %r: %s", location, exc)
            place = {}
        set_phone_region(place.get("country_code"))
        log.info("Location: %s (country %s)", place.get("name", location),
                 place.get("country_code") or "unknown")
        leads: list[dict] = []
        share = 0.70 / len(categories)
        try:
            for i, category in enumerate(categories):
                label = category.replace("_", " ")
                prefix = f"({i + 1}/{len(categories)}) {label}: " if many else ""
                base = i * share

                progress("osm", f"{prefix}Collecting from OpenStreetMap...", base)
                osm = step(f"OpenStreetMap ({label})", collect_from_osm,
                           category, location, osm_max, fallback=[])
                progress("detail", f"{len(osm)} found on OpenStreetMap", None)

                if use_google_maps:
                    progress("maps", f"{prefix}Collecting from Google Maps...", base + share * 0.15)
                    maps = step(f"Google Maps ({label})", maps_module.collect_from_google_maps,
                                category, location, maps_max, fallback=[])
                    progress("detail", f"{len(maps)} found on Google Maps", None)
                else:
                    maps = []
                result.osm_count += len(osm)
                result.maps_count += len(maps)

                progress("merge", f"{prefix}Merging & deduplicating...", base + share * 0.95)
                merged = step(f"Merging ({label})", merge_and_deduplicate, osm, maps,
                              fallback=osm + maps)
                progress("detail", f"{len(merged)} unique businesses", None)
                leads += merged
        except KeyboardInterrupt:
            result.stopped_early = True
            progress("warning", "Collection stopped early; continuing with what was found.", None)

        if many and leads:
            progress("merge", "Merging & deduplicating across categories...", 0.70)
            leads = step("Merging across categories", merge_and_deduplicate, leads, [],
                         fallback=leads)
        result.leads = leads
        if not leads:
            progress("done", "No businesses were found.", 1.0)
            return result

        # 2. Phone numbers (60% - 72%) ----------------------------------------
        missing = [b for b in leads if not b.get("phone")]
        if missing and use_google_maps and config.PHONE_LOOKUP_MAX > 0:
            n = min(len(missing), config.PHONE_LOOKUP_MAX)
            progress("phones", f"Finding phone numbers on Google Maps ({n} businesses)...", 0.60)
            try:
                stats = step("Phone lookup", maps_module.lookup_missing_details, missing, location,
                             config.PHONE_LOOKUP_MAX, fallback={})
            except KeyboardInterrupt:
                result.stopped_early = True
                stats = {}
                progress("warning", "Phone lookup stopped early; continuing.", None)
            result.phones_looked_up = stats.get("looked_up", 0)
            result.phones_found = stats.get("phones_found", 0)
            progress("detail", f"{result.phones_found} of {result.phones_looked_up} "
                               "phone numbers found", None)

        # 3. Enrich (72% - 90%) ------------------------------------------------
        with_site = sum(1 for b in leads if b.get("website"))
        progress("enrich", f"Enriching with social media ({with_site} websites to check)...", 0.72)
        try:
            step("Enrichment", enrich_with_social_and_contact, leads, fallback=leads)
        except KeyboardInterrupt:
            result.stopped_early = True
            progress("warning", "Enrichment stopped early; continuing without the rest.", None)

        # 4. Filter and score (90% - 95%) -------------------------------------
        progress("score", f"Scoring leads ({len(leads)} businesses)...", 0.90)
        rules = list(parsed["filters"])
        # A phone number is required for every lead (unless the user asked for
        # businesses WITHOUT a phone, which would contradict it).
        if config.REQUIRE_PHONE and "no_phone" not in rules and "has_phone" not in rules:
            rules.append("has_phone")
            result.dropped_no_phone = sum(1 for b in leads if not b.get("phone"))
        matched = step("Filtering", filter_leads, leads, rules, fallback=None)
        if matched is None:  # e.g. an invalid rule: keep everything, still scored
            step("Scoring", score_leads, leads)
            matched = sorted(leads, key=lambda b: b.get("lead_score") or 0, reverse=True)
            result.filters_applied = False
            progress("warning", "Filters could not be applied; showing all businesses.", None)
        result.matched = matched
        progress("detail", f"{len(matched)} of {len(leads)} match the filters", None)

        # 5. Export (95% - 100%) ----------------------------------------------
        progress("export", "Building Excel file...", 0.95)
        label = "all" if parsed["category"] == "all" else "_".join(categories[:3])
        # Nothing matched: export every lead that still meets the phone requirement.
        to_export = matched or filter_leads(
            leads, ["has_phone"] if config.REQUIRE_PHONE and "no_phone" not in rules else [])
        result.exported = to_export
        result.output_path = step("Excel export", export_to_excel, to_export,
                                  category=label, location=location)
        if result.output_path is None:  # don't lose the work
            backup = config.OUTPUT_DIR / build_filename(label, location).replace(".xlsx", ".json")
            result.output_path = step("Backup save", _save_json, to_export, backup)

        progress("done", "Done.", 1.0)
        return result
    finally:
        logging.getLogger().removeHandler(forwarder)
        result.seconds = time.monotonic() - started
        log.info("Pipeline end: total=%d matched=%d output=%s errors=%d",
                 len(result.leads), len(result.matched), result.output_path, len(result.errors))
