"""Risk level of the 2-week-ahead forecast against MEM thresholds (DESIGN.md §6.3).

Rule (shown in the UI): with the active horizon-2 model's latest forecast point P and the
MEM levels of the season containing the target week,
  P < epidemic threshold → low; epidemic threshold ≤ P < high intensity → moderate;
  P ≥ high intensity → high.
Countries without usable thresholds for that season are not assessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import Engine, text

from ei_pipeline.detection import config as cfg


@dataclass
class RiskRow:
    iso3: str
    assessed_week: date
    target_week: date
    risk_level: str
    rule: str
    forecast_point: float
    forecast_lo80: float | None
    forecast_hi80: float | None
    model_type: str
    forecast_id: int
    season_start: date


def risk_level(point: float, epidemic: float, high: float) -> str:
    if point < epidemic:
        return "low"
    return "moderate" if point < high else "high"


def load_forecasts(engine: Engine, disease_id: int) -> pd.DataFrame:
    """Latest-origin forecasts of the active model at the risk horizon."""
    with engine.connect() as c:
        return pd.read_sql(text("""
            SELECT f.id, f.iso3, f.origin_week, f.target_week, f.point, f.lo80, f.hi80,
                   mv.model_type
            FROM forecasts f JOIN model_versions mv ON mv.id = f.model_version_id
            WHERE mv.disease_id = :d AND mv.is_active AND mv.horizon_weeks = :h
              AND f.origin_week = (SELECT max(f2.origin_week) FROM forecasts f2
                                   WHERE f2.model_version_id = mv.id)
        """), c, params={"d": disease_id, "h": cfg.RISK_HORIZON})


def assess(forecasts: pd.DataFrame, thresholds: dict[tuple[str, date], object],
           season_start_of) -> list[RiskRow]:
    """`thresholds` maps (iso3, season_start) → ThresholdRow (usable ones only);
    `season_start_of(iso3, week)` gives the season start of a week for that country."""
    out = []
    for f in forecasts.itertuples():
        start = season_start_of(f.iso3, f.target_week)
        t = thresholds.get((f.iso3, start)) if start else None
        if t is None:
            continue
        level = risk_level(f.point, t.epidemic_threshold, t.high)
        rule = (f"2-week forecast {f.point:.1%} vs {t.season} MEM epidemic threshold "
                f"{t.epidemic_threshold:.1%} and high intensity {t.high:.1%}")
        out.append(RiskRow(
            iso3=f.iso3, assessed_week=f.origin_week, target_week=f.target_week,
            risk_level=level, rule=rule, forecast_point=float(f.point),
            forecast_lo80=None if pd.isna(f.lo80) else float(f.lo80),
            forecast_hi80=None if pd.isna(f.hi80) else float(f.hi80),
            model_type=f.model_type, forecast_id=int(f.id), season_start=start,
        ))
    return out
