"""`ei detect run`: thresholds → risk → anomalies → hotspots, stored per run.

Outputs are fully recomputable, so each run replaces the previous thresholds, anomalies
and hotspots for the disease in one transaction and records a `detection_runs` row
(settings + counts). Risk rows are kept across runs (one per country and assessed week;
a rerun replaces the same week) because their history drives the risk-escalation alert.
Alerts (M7) are then derived from the stored outputs. Run after `ei forecast run` so risk
uses the latest active forecasts.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine, delete, insert, update

from ei_db.models import (
    Anomaly,
    DetectionRun,
    HotspotResult,
    RiskAssessment,
    SeasonalThreshold,
)
from ei_pipeline.db import session_scope
from ei_pipeline.detection import config as cfg
from ei_pipeline.detection.anomalies import compute_anomalies
from ei_pipeline.detection.data import load_detection_data, season_first_week
from ei_pipeline.detection.hotspots import compute_hotspots
from ei_pipeline.detection.risk import assess, load_forecasts
from ei_pipeline.detection.thresholds import compute_thresholds
from ei_pipeline.detection.weights import load_geography
from ei_pipeline.forecasting.run import _git_sha
from ei_pipeline.intelligence.alerts import generate_alerts

log = logging.getLogger(__name__)
CHUNK = 5000


def _insert(s, model, rows: list[dict]) -> None:
    for i in range(0, len(rows), CHUNK):
        s.execute(insert(model), rows[i:i + CHUNK])


def _season_start_of(countries: pd.DataFrame):
    season_type = countries.set_index("iso3")["flu_season"].to_dict()

    def f(iso3: str, week) -> object:
        st = season_type.get(iso3)
        if not st:
            return None
        y, w, _ = week.isocalendar()
        if st == "NH" and w < cfg.NH_START_WEEK:
            y -= 1
        return season_first_week(y, st)
    return f


def run_detection(engine: Engine) -> dict:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    data = load_detection_data(engine)
    geo = load_geography(engine)
    timings["load"] = time.perf_counter() - t0

    t = time.perf_counter()
    thresholds, not_assessed = compute_thresholds(data.weekly, data.countries,
                                                  data.reference_week, data.latest_week)
    timings["thresholds"] = time.perf_counter() - t

    usable = {(r.iso3, r.season_start): r for r in thresholds if r.quality_note is None}
    risk = assess(load_forecasts(engine, data.disease_id), usable,
                  _season_start_of(data.countries))

    t = time.perf_counter()
    anomalies, anomaly_stats = compute_anomalies(data.weekly)
    timings["anomalies"] = time.perf_counter() - t

    t = time.perf_counter()
    hotspots = compute_hotspots(data.weekly, geo, data.latest_week)
    timings["hotspots"] = time.perf_counter() - t

    run_key = f"{data.reference_week:%Y%m%d}-{datetime.now(UTC):%H%M%S}"
    with session_scope(engine) as s:
        run_id = s.execute(insert(DetectionRun).returning(DetectionRun.id).values(
            disease_id=data.disease_id, run_key=run_key, reference_week=data.reference_week,
            latest_week=data.latest_week, git_sha=_git_sha(),
        )).scalar_one()
        for model in (Anomaly, HotspotResult, SeasonalThreshold):
            s.execute(delete(model).where(model.disease_id == data.disease_id))
        assessed = {r.assessed_week for r in risk}
        if assessed:
            s.execute(delete(RiskAssessment).where(
                RiskAssessment.disease_id == data.disease_id,
                RiskAssessment.assessed_week.in_(assessed)))

        base = {"run_id": run_id, "disease_id": data.disease_id}
        th_ids = {}
        for r in thresholds:
            th_ids[(r.iso3, r.season_start)] = s.execute(
                insert(SeasonalThreshold).returning(SeasonalThreshold.id)
                .values(**base, method="mem", **asdict(r))).scalar_one()
        _insert(s, RiskAssessment, [
            {**base, **{k: v for k, v in asdict(r).items() if k != "season_start"},
             "threshold_id": th_ids[(r.iso3, r.season_start)]} for r in risk])
        _insert(s, Anomaly, [{**base, "metric": "positivity", **asdict(a)} for a in anomalies])
        _insert(s, HotspotResult, [{**base, "weights_spec": cfg.WEIGHTS_SPEC, **asdict(h)}
                                   for h in hotspots])

        current = [r for r in thresholds
                   if r.season_start == max(x.season_start for x in thresholds
                                            if x.iso3 == r.iso3)]
        summary = {
            "settings": {k: (str(v) if not isinstance(v, int | float | str | tuple) else v)
                         for k, v in vars(cfg).items() if k.isupper()},
            "thresholds": {"rows": len(thresholds),
                           "countries_current_usable": sum(r.quality_note is None
                                                           for r in current),
                           "countries_current_flagged": sum(r.quality_note is not None
                                                            for r in current),
                           "not_assessed": not_assessed},
            "risk": {lvl: sum(r.risk_level == lvl for r in risk)
                     for lvl in ("low", "moderate", "high")},
            "anomalies": {"seasonal_ewma": sum(a.method == "seasonal_ewma" for a in anomalies),
                          "isolation_forest": sum(a.method == "isolation_forest"
                                                  for a in anomalies),
                          **anomaly_stats},
            "hotspots": {"rows": len(hotspots),
                         "windows": len({h.window_end for h in hotspots})},
            "seconds": {k: round(v, 1) for k, v in timings.items()},
        }

    # Alerts read the committed outputs (and the full risk history).
    t = time.perf_counter()
    summary["alerts"] = generate_alerts(engine, data.disease_id, run_id)
    summary["seconds"]["alerts"] = round(time.perf_counter() - t, 1)
    with session_scope(engine) as s:
        s.execute(update(DetectionRun).where(DetectionRun.id == run_id)
                  .values(finished_at=datetime.now(UTC), summary=summary))

    return {"run_key": run_key, "reference_week": str(data.reference_week),
            "thresholds": summary["thresholds"]["rows"],
            "thresholds_current_usable": summary["thresholds"]["countries_current_usable"],
            "risk": summary["risk"], "anomalies": summary["anomalies"],
            "hotspots": summary["hotspots"], "alerts": summary["alerts"],
            "seconds": summary["seconds"]}
