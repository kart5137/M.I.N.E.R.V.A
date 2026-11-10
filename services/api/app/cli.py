"""Command-line access to API services that the weekly job needs (M8).

    python -m app.cli report [--scope global|country] [--iso3 X] [--region R] [--weeks N]

Builds a template report from stored data exactly as POST /reports/generate does (same
facts, same Markdown, same reuse of an identical report), without going through HTTP, so
the scheduled pipeline does not depend on the web service being awake.
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import Engine

from app.core.db import get_engine
from app.core.errors import ApiError
from app.queries.common import load_disease
from app.reports import service
from app.schemas.intelligence import GenerateRequest
from ei_db import make_session_factory


def main(argv: list[str] | None = None, engine: Engine | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="generate a template report from stored data")
    rep.add_argument("--disease", default="influenza")
    rep.add_argument("--scope", choices=("global", "country"), default="global")
    rep.add_argument("--iso3")
    rep.add_argument("--region")
    rep.add_argument("--weeks", type=int, default=4)
    args = parser.parse_args(argv)

    req = GenerateRequest(scope=args.scope, iso3=args.iso3, region=args.region,
                          weeks=args.weeks)
    with make_session_factory(engine or get_engine())() as session:
        try:
            ctx = load_disease(session, args.disease)
            report, reused = service.generate(session, ctx, req)
        except ApiError as e:
            print(f"error: {e.code}: {e.message}", file=sys.stderr)
            return 2
    print(json.dumps({"id": report.id, "title": report.title, "reused": reused,
                      "inputs_sha256": report.inputs_sha256, "alerts": report.alerts},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
