"""`ei` command-line entry point for pipeline jobs.

    ei ingest reference              seed data sources and diseases
    ei ingest boundaries [--refresh] Natural Earth → countries
    ei ingest population [--refresh] World Bank → population_annual
    ei ingest health [--refresh]     World Bank → health_indicators
    ei ingest flunet [--refresh]     WHO FluNet → surveillance_weekly
    ei ingest all [--refresh]        all of the above, in order
    ei forecast run [--fast]         backtest, select, train and store forecasts (M5)
    ei detect run                    thresholds, risk, anomalies, hotspots (M6)
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
from ei_pipeline.ingest.flunet import ingest_flunet
from ei_pipeline.ingest.health import ingest_health
from ei_pipeline.ingest.population import ingest_population

STEPS = ("reference", "boundaries", "population", "health", "flunet")
SUMMARY_KEYS = ("inserted", "updated", "unchanged", "revisions_recorded", "rows_excluded",
                "reference_week", "coverage_tiers", "areas", "latest_year",
                "countries_without_population", "indicators")


def _run_step(engine, step: str, refresh: bool) -> dict:
    if step == "reference":
        with session_scope(engine) as s:
            return seed_reference(s)
    job = {"boundaries": ingest_boundaries, "population": ingest_population,
           "health": ingest_health, "flunet": ingest_flunet}[step]
    return job(engine, refresh=refresh)


def _summary(report: dict) -> dict:
    out = {k: report[k] for k in SUMMARY_KEYS if k in report}
    if "validation" in report:
        out["rows_excluded"] = report["validation"]["rows_excluded"]
    if isinstance(out.get("countries_without_population", "indicators"), list):
        out["countries_without_population"] = len(out["countries_without_population"])
    if isinstance(out.get("indicators"), dict):
        out["indicators"] = {k: v["countries_with_value"] for k, v in out["indicators"].items()}
    return out or report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ei", description="Epidemic Intelligence pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="load source data into the database")
    ingest.add_argument("step", choices=(*STEPS, "all"))
    ingest.add_argument("--refresh", action="store_true", help="re-download source files")
    forecast = sub.add_parser("forecast", help="backtest, train and store forecasts")
    forecast.add_argument("step", choices=("run",))
    forecast.add_argument("--fast", action="store_true",
                          help="small models for a quick check (not for real use)")
    detect = sub.add_parser("detect", help="thresholds, risk, anomalies and hotspots")
    detect.add_argument("step", choices=("run",))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine = make_engine()
    if args.command == "forecast":
        from ei_pipeline.forecasting.run import run_forecast  # heavy imports: only when used

        t0 = time.perf_counter()
        summary = run_forecast(engine, fast=args.fast)
        print(f"[forecast] {time.perf_counter() - t0:.1f}s {json.dumps(summary, default=str)}")
        return 0
    if args.command == "detect":
        from ei_pipeline.detection.run import run_detection

        t0 = time.perf_counter()
        summary = run_detection(engine)
        print(f"[detect] {time.perf_counter() - t0:.1f}s {json.dumps(summary, default=str)}")
        return 0
    steps = STEPS if args.step == "all" else (args.step,)
    for step in steps:
        t0 = time.perf_counter()
        report = _run_step(engine, step, args.refresh)
        print(f"[{step}] {time.perf_counter() - t0:.1f}s "
              f"{json.dumps(_summary(report), default=str)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
