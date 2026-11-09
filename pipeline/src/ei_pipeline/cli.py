"""`ei` command-line entry point for pipeline jobs.

    ei ingest reference              seed data sources and diseases
    ei ingest boundaries [--refresh] Natural Earth → countries
    ei ingest population [--refresh] World Bank → population_annual
    ei ingest flunet [--refresh]     WHO FluNet → surveillance_weekly
    ei ingest all [--refresh]        all of the above, in order
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
from ei_pipeline.ingest.population import ingest_population

STEPS = ("reference", "boundaries", "population", "flunet")
SUMMARY_KEYS = ("inserted", "updated", "unchanged", "revisions_recorded", "rows_excluded",
                "reference_week", "coverage_tiers", "areas", "latest_year",
                "countries_without_population")


def _run_step(engine, step: str, refresh: bool) -> dict:
    if step == "reference":
        with session_scope(engine) as s:
            return seed_reference(s)
    job = {"boundaries": ingest_boundaries, "population": ingest_population,
           "flunet": ingest_flunet}[step]
    return job(engine, refresh=refresh)


def _summary(report: dict) -> dict:
    out = {k: report[k] for k in SUMMARY_KEYS if k in report}
    if "validation" in report:
        out["rows_excluded"] = report["validation"]["rows_excluded"]
    if isinstance(out.get("countries_without_population"), list):
        out["countries_without_population"] = len(out["countries_without_population"])
    return out or report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ei", description="Epidemic Intelligence pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="load source data into the database")
    ingest.add_argument("step", choices=(*STEPS, "all"))
    ingest.add_argument("--refresh", action="store_true", help="re-download source files")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine = make_engine()
    steps = STEPS if args.step == "all" else (args.step,)
    for step in steps:
        t0 = time.perf_counter()
        report = _run_step(engine, step, args.refresh)
        print(f"[{step}] {time.perf_counter() - t0:.1f}s "
              f"{json.dumps(_summary(report), default=str)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
