"""Anomalous weeks: positivity unusually high for the country and time of year
(DESIGN.md §6.4).

Primary method `seasonal_ewma`:

1. Baseline for week (ISO year y, ISO week w): valid weekly positivity in ISO weeks
   w−1..w+1 of earlier years, outside the COVID window, from the latest 5 years that have
   any such value (needs ≥ 3 years). Expected = median, upper band = 90th percentile.
2. Standardised residual r = (observed − expected) / s, with s = (p90 − median) / 1.2816
   (the normal-equivalent spread) floored at 2 percentage points.
3. EWMA control chart on r (λ = 0.3) with limit L·√(λ / (2 − λ)), L = 3. The chart runs
   over consecutive valid weeks from the end of the COVID window; gaps are skipped.
4. A week is anomalous when observed > upper band **and** the EWMA exceeds its limit.
   Severity from r: < 3 moderate, 3–5 high, ≥ 5 severe.

Secondary `isolation_forest`: per country, an Isolation Forest on (positivity,
log specimens, 1-week change in positivity) over its non-COVID history flags unusual
weeks of any kind. Reported separately; never an alert trigger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ei_pipeline.detection import config as cfg

Z90 = 1.2815515655446004


@dataclass
class AnomalyRow:
    iso3: str
    week_start: date
    method: str
    observed: float
    expected: float | None
    upper_band: float | None
    score: float
    ewma: float | None
    ewma_limit: float | None
    specimens_tested: int | None
    severity: str | None
    is_provisional: bool


def severity_of(r: float) -> str:
    for cut, name in cfg.SEVERITY_CUTS:
        if r >= cut:
            return name
    return cfg.SEVERITY_CUTS[-1][1]


def seasonal_baseline(rows: pd.DataFrame) -> pd.DataFrame:
    """Add `expected`, `upper`, `n_years` to a country's valid weekly rows."""
    rows = rows.copy()
    iso = rows["week_start"].dt.isocalendar()
    rows["iso_year"], rows["iso_week"] = iso["year"].astype(int), iso["week"].astype(int)
    hist = rows[rows["p"].notna() & ~rows["covid"]]
    # (iso_year, iso_week) → positivity for quick lookups; week 53 maps to 52 in years
    # without one by searching w−1..w+1.
    lookup: dict[int, dict[int, float]] = {}
    for y, w, p in zip(hist["iso_year"], hist["iso_week"], hist["p"], strict=True):
        lookup.setdefault(y, {})[w] = p
    years = sorted(lookup)

    exp, up, ny = [], [], []
    hw = cfg.BASELINE_WEEK_HALFWIDTH
    for y, w in zip(rows["iso_year"], rows["iso_week"], strict=True):
        vals, used = [], 0
        for yy in reversed(years):
            if yy >= y:
                continue
            got = [lookup[yy][k] for k in range(w - hw, w + hw + 1) if k in lookup[yy]]
            if got:
                vals += got
                used += 1
                if used == cfg.BASELINE_YEARS:
                    break
        if used >= cfg.BASELINE_MIN_YEARS:
            exp.append(float(np.median(vals)))
            up.append(float(np.quantile(vals, cfg.UPPER_QUANTILE)))
        else:
            exp.append(np.nan)
            up.append(np.nan)
        ny.append(used)
    rows["expected"], rows["upper"], rows["n_years"] = exp, up, ny
    return rows


def ewma_chart(rows: pd.DataFrame) -> pd.DataFrame:
    """Standardised residual and EWMA over consecutive valid weeks after COVID."""
    rows = rows.copy()
    spread = ((rows["upper"] - rows["expected"]) / Z90).clip(
        lower=cfg.RESIDUAL_SCALE_FLOOR_PP / 100)
    rows["r"] = (rows["p"] - rows["expected"]) / spread
    lam = cfg.EWMA_LAMBDA
    limit = cfg.EWMA_L * np.sqrt(lam / (2 - lam))
    z, out = 0.0, []
    start = pd.Timestamp(cfg.COVID_END)
    for wk, r in zip(rows["week_start"], rows["r"], strict=True):
        if wk <= start or np.isnan(r):
            out.append(np.nan)
            continue
        z = lam * r + (1 - lam) * z
        out.append(z)
    rows["ewma"], rows["ewma_limit"] = out, limit
    return rows


def seasonal_ewma_anomalies(iso3: str, rows: pd.DataFrame) -> tuple[list[AnomalyRow],
                                                                    pd.DataFrame]:
    valid = rows[rows["p"].notna()].sort_values("week_start")
    if valid.empty:
        return [], valid
    chart = ewma_chart(seasonal_baseline(valid))
    flagged = chart[(chart["week_start"] >= pd.Timestamp(cfg.ANOMALIES_FROM))
                    & (chart["p"] > chart["upper"]) & (chart["ewma"] > chart["ewma_limit"])]
    out = [AnomalyRow(
        iso3=iso3, week_start=r.week_start.date(), method="seasonal_ewma",
        observed=float(r.p), expected=float(r.expected), upper_band=float(r.upper),
        score=float(r.r), ewma=float(r.ewma), ewma_limit=float(r.ewma_limit),
        specimens_tested=int(r.tests), severity=severity_of(r.r),
        is_provisional=bool(r.is_provisional),
    ) for r in flagged.itertuples()]
    return out, chart


def isolation_forest_anomalies(iso3: str, rows: pd.DataFrame) -> list[AnomalyRow]:
    valid = rows[rows["p"].notna() & ~rows["covid"]].sort_values("week_start").copy()
    if len(valid) < cfg.IFOREST_MIN_WEEKS:
        return []
    valid["log_tests"] = np.log1p(valid["tests"])
    valid["dp"] = valid["p"].diff().fillna(0)
    x = valid[["p", "log_tests", "dp"]].to_numpy()
    model = IsolationForest(contamination=cfg.IFOREST_CONTAMINATION,
                            random_state=cfg.IFOREST_SEED, n_estimators=200).fit(x)
    valid["flag"] = model.predict(x) == -1
    valid["score"] = -model.score_samples(x)
    recent = valid[valid["flag"] & (valid["week_start"] >= pd.Timestamp(cfg.ANOMALIES_FROM))]
    return [AnomalyRow(
        iso3=iso3, week_start=r.week_start.date(), method="isolation_forest",
        observed=float(r.p), expected=None, upper_band=None, score=float(r.score),
        ewma=None, ewma_limit=None, specimens_tested=int(r.tests), severity=None,
        is_provisional=bool(r.is_provisional),
    ) for r in recent.itertuples()]


def compute_anomalies(weekly: pd.DataFrame) -> tuple[list[AnomalyRow], dict]:
    rows_out: list[AnomalyRow] = []
    stats = {"countries_with_baseline": 0, "weeks_checked": 0}
    for iso3, rows in weekly.groupby("iso3", sort=True):
        primary, chart = seasonal_ewma_anomalies(iso3, rows)
        if not chart.empty:
            checked = chart[(chart["week_start"] >= pd.Timestamp(cfg.ANOMALIES_FROM))
                            & chart["expected"].notna()]
            stats["weeks_checked"] += len(checked)
            stats["countries_with_baseline"] += int(len(checked) > 0)
        rows_out += primary
        rows_out += isolation_forest_anomalies(iso3, rows)
    return rows_out, stats
