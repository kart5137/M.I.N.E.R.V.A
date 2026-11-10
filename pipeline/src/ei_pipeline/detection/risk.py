"""Risk level of the 2-week-ahead forecast against MEM thresholds (DESIGN.md §6.3).

Rule (shown in the UI): with the active horizon-2 model's latest forecast point P and the
MEM levels of the season containing the target week,
  P < epidemic threshold → low; epidemic threshold ≤ P < high intensity → moderate;
  P ≥ high intensity → high.
Countries without usable thresholds for that season are not assessed.

Dengue (D5) uses the endemic channel of the target week instead (`assess_channel`):
  P < top of the channel (75th percentile) → low; up to the 90th percentile → moderate;
  at or above it → high. Both levels are at least one weekly case (one case per 100,000
  population, as incidence), so a country with usually zero cases is not "above its usual
  range" on a fraction of a forecast case.
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
    season: str
    epidemic_threshold: float
    high_threshold: float
    season_start: date | None
    method: str = "mem"


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


def fmt_value(v: float, metric: str = "positivity") -> str:
    """Positivity as a percentage; incidence as cases per 100,000."""
    if metric == "positivity":
        return f"{v:.1%}"
    if 0 < abs(v) < 0.005:
        return "< 0.01 per 100k"
    d = 2 if abs(v) < 10 else 1 if abs(v) < 100 else 0
    return f"{v:,.{d}f} per 100k"


def year_ranges(years: list[int]) -> str:
    """[2019, 2020, 2021, 2023] → "2019–2021, 2023"."""
    out, start = [], None
    for i, y in enumerate(years):
        start = y if start is None else start
        if i + 1 == len(years) or years[i + 1] != y + 1:
            out.append(str(y) if start == y else f"{start}–{y}")
            start = None
    return ", ".join(out)


def assess_channel(forecasts: pd.DataFrame, channel: dict[tuple[str, date], object],
                   one_case: dict[str, float], metric: str = "incidence") -> list[RiskRow]:
    """`channel` maps (iso3, week_start) → ChannelRow; `one_case` maps iso3 → one case
    per 100,000 population (incidence of a single case)."""
    out = []
    for f in forecasts.itertuples():
        ch = channel.get((f.iso3, f.target_week))
        if ch is None:
            continue
        floor = one_case.get(f.iso3, 0.0)
        top, high = max(ch.q75, floor), max(ch.p90, floor)
        rule = (f"2-week forecast {fmt_value(f.point, metric)} vs the endemic channel of "
                f"week {ch.iso_week} from {year_ranges(ch.years_used)} (highest year "
                f"{year_ranges(ch.excluded_years)} left out): top of the channel "
                f"{fmt_value(top, metric)}, 90th percentile {fmt_value(high, metric)}")
        out.append(RiskRow(
            iso3=f.iso3, assessed_week=f.origin_week, target_week=f.target_week,
            risk_level=risk_level(f.point, top, high), rule=rule,
            forecast_point=float(f.point),
            forecast_lo80=None if pd.isna(f.lo80) else float(f.lo80),
            forecast_hi80=None if pd.isna(f.hi80) else float(f.hi80),
            model_type=f.model_type, forecast_id=int(f.id), season=str(ch.year),
            epidemic_threshold=top, high_threshold=high, season_start=None,
            method="endemic_channel",
        ))
    return out


def assess(forecasts: pd.DataFrame, thresholds: dict[tuple[str, date], object],
           season_start_of, metric: str = "positivity") -> list[RiskRow]:
    """`thresholds` maps (iso3, season_start) → ThresholdRow (usable ones only);
    `season_start_of(iso3, week)` gives the season start of a week for that country."""
    out = []
    for f in forecasts.itertuples():
        start = season_start_of(f.iso3, f.target_week)
        t = thresholds.get((f.iso3, start)) if start else None
        if t is None:
            continue
        level = risk_level(f.point, t.epidemic_threshold, t.high)
        rule = (f"2-week forecast {fmt_value(f.point, metric)} vs {t.season} MEM epidemic "
                f"threshold {fmt_value(t.epidemic_threshold, metric)} and high intensity "
                f"{fmt_value(t.high, metric)}")
        out.append(RiskRow(
            iso3=f.iso3, assessed_week=f.origin_week, target_week=f.target_week,
            risk_level=level, rule=rule, forecast_point=float(f.point),
            forecast_lo80=None if pd.isna(f.lo80) else float(f.lo80),
            forecast_hi80=None if pd.isna(f.hi80) else float(f.hi80),
            model_type=f.model_type, forecast_id=int(f.id), season=t.season,
            epidemic_threshold=t.epidemic_threshold, high_threshold=t.high,
            season_start=start,
        ))
    return out
