"""`ei` command-line entry point for pipeline jobs.

    ei ingest reference              seed data sources and diseases
    ei ingest boundaries [--refresh] Natural Earth → countries
    ei ingest population [--refresh] World Bank → population_annual
    ei ingest health [--refresh]     World Bank → health_indicators
    ei ingest flunet [--refresh]     WHO FluNet → surveillance_weekly
    ei ingest dengue [--refresh]     WHO dengue → surveillance_weekly / _monthly (D1)
    ei ingest weather [--refresh] [--budget N] [--backfill-only]
                                     Open-Meteo ERA5 → weather_weekly for dengue areas
                                     (D3); resumable within N weighted API calls
    ei ingest all [--refresh]        all of the above, in order
    ei forecast run [--fast] [--disease D]
                                     backtest, select, train and store forecasts (M5;
                                     dengue incidence D4); default: every disease
    ei detect run [--disease D]      thresholds, risk, anomalies, hotspots (M6), alerts (M7)
    ei prune [--keep N]              drop per-country detail of old forecast runs (M8)
    ei weekly [--fast]               the scheduled job: ingest (FluNet, dengue refreshed,
                                     weather topped up), then forecast and detect for
                                     influenza and dengue, prune (M8)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from ei_db import make_engine
from ei_pipeline.catalog import seed_reference
from ei_pipeline.db import session_scope
from ei_pipeline.ingest.boundaries import ingest_boundaries
from ei_pipeline.ingest.dengue import ingest_dengue
from ei_pipeline.ingest.flunet import ingest_flunet
from ei_pipeline.ingest.health import ingest_health
from ei_pipeline.ingest.population import ingest_population
from ei_pipeline.ingest.weather import DEFAULT_BUDGET, ingest_weather
from ei_pipeline.maintenance import DEFAULT_KEEP, prune_runs

log = logging.getLogger(__name__)

STEPS = ("reference", "boundaries", "population", "health", "flunet", "dengue", "weather")
#: Surveillance sources re-downloaded by every weekly run; reference files only when
#: missing.
REFRESHED = ("flunet", "dengue")
#: Steps whose failure is logged without stopping the weekly job. Weather: dengue
#: forecasting (D4) reads the weather already stored; a missed top-up only leaves the
#: newest weeks without weather features (tree models handle missing values).
OPTIONAL = ("weather",)
#: Diseases forecast and scanned by the weekly job, in order: influenza first so that its
#: outputs are stored before the dengue steps run.
DISEASES = ("influenza", "dengue")
SUMMARY_KEYS = ("inserted", "updated", "unchanged", "revisions_recorded", "rows_excluded",
                "reference_week", "reference_month", "coverage_tiers", "areas", "latest_year",
                "countries_without_population", "indicators", "latest_week",
                "areas_updated", "areas_still_behind", "areas_failed", "weighted_calls",
                "stopped_early")


def _run_step(engine, step: str, refresh: bool, **weather_opts) -> dict:
    if step == "reference":
        with session_scope(engine) as s:
            return seed_reference(s)
    if step == "weather":
        return ingest_weather(engine, refresh=refresh, **weather_opts)
    job = {"boundaries": ingest_boundaries, "population": ingest_population,
           "health": ingest_health, "flunet": ingest_flunet, "dengue": ingest_dengue}[step]
    return job(engine, refresh=refresh)


def _summary(report: dict) -> dict:
    out = {k: report[k] for k in SUMMARY_KEYS if k in report}
    if "validation" in report:
        out["rows_excluded"] = report["validation"]["rows_excluded"]
    if isinstance(out.get("countries_without_population", "indicators"), list):
        out["countries_without_population"] = len(out["countries_without_population"])
    if isinstance(out.get("areas_failed"), dict):
        out["areas_failed"] = len(out["areas_failed"])
    if isinstance(out.get("indicators"), dict):
        out["indicators"] = {k: v["countries_with_value"] for k, v in out["indicators"].items()}
    return out or report


def _timed(label: str, fn) -> dict:
    t0 = time.perf_counter()
    out = fn()
    print(f"[{label}] {time.perf_counter() - t0:.1f}s {json.dumps(out, default=str)}",
          flush=True)
    return out


def _weekly(engine, *, fast: bool, keep: int) -> int:
    """The scheduled job. Reference files (boundaries, World Bank) are downloaded only when
    missing; surveillance sources (REFRESHED) are always re-downloaded. Any failure stops
    the job (non-zero exit)."""
    from ei_pipeline.detection.run import run_detection
    from ei_pipeline.forecasting.run import run_forecast

    for step in STEPS:
        try:
            _timed(step, lambda s=step: _summary(_run_step(engine, s, refresh=s in REFRESHED)))
        except Exception:
            if step not in OPTIONAL:
                raise
            log.exception("Optional step %s failed; continuing", step)
    for disease in DISEASES:
        _timed(f"forecast:{disease}", lambda d=disease: {
            k: v for k, v in run_forecast(engine, disease=d, fast=fast).items()
            if k in ("run_key", "reference_week", "forecasts", "active")})
        _timed(f"detect:{disease}", lambda d=disease: run_detection(engine, d))
    _timed("prune", lambda: prune_runs(engine, keep))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ei", description="M.I.N.E.R.V.A. pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="load source data into the database")
    ingest.add_argument("step", choices=(*STEPS, "all"))
    ingest.add_argument("--refresh", action="store_true", help="re-download source files")
    ingest.add_argument("--budget", type=float, default=DEFAULT_BUDGET,
                        help="weather: weighted Open-Meteo calls this run may use")
    ingest.add_argument("--max-minutes", type=float, default=None,
                        help="weather: no new requests after this many minutes")
    ingest.add_argument("--backfill-only", action="store_true",
                        help="weather: only areas whose history is still incomplete")
    forecast = sub.add_parser("forecast", help="backtest, train and store forecasts")
    forecast.add_argument("step", choices=("run",))
    forecast.add_argument("--fast", action="store_true",
                          help="small models for a quick check (not for real use)")
    forecast.add_argument("--disease", choices=(*DISEASES, "all"), default="all")
    detect = sub.add_parser("detect", help="thresholds, risk, anomalies and hotspots")
    detect.add_argument("step", choices=("run",))
    detect.add_argument("--disease", choices=(*DISEASES, "all"), default="all")
    prune = sub.add_parser("prune", help="drop per-country detail of old forecast runs")
    prune.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                       help=f"forecast runs to keep in full (default {DEFAULT_KEEP})")
    weekly = sub.add_parser("weekly", help="ingest, forecast, detect and prune in order")
    weekly.add_argument("--fast", action="store_true", help="small forecast models (CI checks)")
    weekly.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine = make_engine()
    if args.command == "weekly":
        return _weekly(engine, fast=args.fast, keep=args.keep)
    if args.command == "prune":
        print(f"[prune] {json.dumps(prune_runs(engine, args.keep))}")
        return 0
    if args.command == "forecast":
        from ei_pipeline.forecasting.run import run_forecast  # heavy imports: only when used

        for d in (DISEASES if args.disease == "all" else (args.disease,)):
            t0 = time.perf_counter()
            summary = run_forecast(engine, disease=d, fast=args.fast)
            print(f"[forecast:{d}] {time.perf_counter() - t0:.1f}s "
                  f"{json.dumps(summary, default=str)}")
        return 0
    if args.command == "detect":
        from ei_pipeline.detection.run import run_detection

        for d in (DISEASES if args.disease == "all" else (args.disease,)):
            t0 = time.perf_counter()
            summary = run_detection(engine, d)
            print(f"[detect:{d}] {time.perf_counter() - t0:.1f}s "
                  f"{json.dumps(summary, default=str)}")
        return 0
    steps = STEPS if args.step == "all" else (args.step,)
    for step in steps:
        t0 = time.perf_counter()
        opts = ({"budget": args.budget, "backfill_only": args.backfill_only,
                 "max_minutes": args.max_minutes}
                if step == "weather" else {})
        report = _run_step(engine, step, args.refresh, **opts)
        print(f"[{step}] {time.perf_counter() - t0:.1f}s "
              f"{json.dumps(_summary(report), default=str)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
