"""Per-country, per-season MEM thresholds from earlier usable seasons (DESIGN.md §6.3).

A season is *usable* when it has ended by the reference week, does not overlap the COVID
window, has a valid positivity (≥ MIN_TESTS specimens) in ≥ 75% of its weeks and at least
one positive week. Thresholds for season S use the latest ≤ 10 usable seasons before S;
with fewer than 3, S gets none. MEM runs on positivity in percent; outputs are stored as
fractions like `surveillance_weekly.positivity`.

Scope (M6 finding): MEM assumes one epidemic per season. It is applied to NH and SH
countries only; for year-round (YR) countries the calendar-year "season" cuts through
several waves and 49 of 70 gave an epidemic threshold above medium intensity, so they
are not assessed. Levels that fail the quality gate (`quality_issue`) are stored with a
note and never used for risk.

Dengue (D4): MEM on weekly incidence per 100,000 (stored as is), with ISO calendar-year
seasons in every country; seasons overlapping the COVID window are used (dengue kept
circulating). A season is usable with incidence in ≥ 75% of its weeks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ei_pipeline.detection import config as cfg
from ei_pipeline.detection.data import (
    covid_disrupted,
    season_first_week,
    season_label,
    season_start_year,
)
from ei_pipeline.detection.mem import memmodel

WEEK = timedelta(weeks=1)


@dataclass
class SeasonSeries:
    year: int
    label: str
    first: date
    last: date
    values: np.ndarray            # positivity in percent, NaN when not valid
    completeness: float
    usable: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class ThresholdRow:
    iso3: str
    season: str
    season_start: date
    epidemic_threshold: float
    post_threshold: float | None
    medium: float
    high: float
    very_high: float
    n_seasons_used: int
    seasons_used: list[str]
    mean_epidemic_weeks: float
    quality_note: str | None


def country_seasons(rows: pd.DataFrame, season_type: str, reference_week: date,
                    spec: cfg.DetectionSpec = cfg.INFLUENZA) -> list[SeasonSeries]:
    """Every season with at least one row, oldest first, on a complete weekly calendar.
    Values are on the MEM scale (positivity in percent; dengue incidence as is)."""
    if rows.empty:
        return []
    years = season_start_year(rows["week_start"], pd.Series(season_type, index=rows.index))
    p_by_week = dict(zip(rows["week_start"].dt.date, rows["p"] * spec.mem_factor, strict=True))
    out = []
    for y in sorted(years.unique()):
        first = season_first_week(int(y), season_type)
        last = season_first_week(int(y) + 1, season_type) - WEEK
        n = (last - first).days // 7 + 1
        values = np.array([p_by_week.get(first + WEEK * i, np.nan) for i in range(n)],
                          dtype=float)
        completeness = float((~np.isnan(values)).mean())
        reasons = []
        if last > reference_week:
            reasons.append("in progress")
        if spec.exclude_covid and covid_disrupted(first, last):
            reasons.append("COVID-19 disruption")
        if completeness < cfg.SEASON_MIN_COMPLETENESS:
            reasons.append(f"only {completeness:.0%} of weeks with ≥ {cfg.MIN_TESTS} specimens"
                           if spec.metric == "positivity" else
                           f"only {completeness:.0%} of weeks with reported cases")
        if not np.nansum(values) > 0:
            reasons.append("no positive weeks")
        out.append(SeasonSeries(year=int(y), label=season_label(int(y), season_type),
                                first=first, last=last, values=values,
                                completeness=completeness, usable=not reasons,
                                reasons=reasons))
    return out


def thresholds_for_country(iso3: str, seasons: list[SeasonSeries], season_type: str,
                           current_year: int, spec: cfg.DetectionSpec = cfg.INFLUENZA
                           ) -> list[ThresholdRow]:
    f = spec.mem_factor
    out = []
    for y in range(cfg.THRESHOLDS_FROM_YEAR, current_year + 1):
        past = [s for s in seasons if s.year < y and s.usable][-10:]
        if len(past) < cfg.MIN_SEASONS_FOR_THRESHOLDS:
            continue
        r = memmodel([s.values for s in past])
        if r is None or not np.isfinite(r.epidemic_threshold):
            continue
        out.append(ThresholdRow(
            iso3=iso3, season=season_label(y, season_type),
            season_start=season_first_week(y, season_type),
            epidemic_threshold=r.epidemic_threshold / f,
            post_threshold=None if r.post_threshold is None else r.post_threshold / f,
            medium=r.medium / f, high=r.high / f, very_high=r.very_high / f,
            n_seasons_used=r.n_seasons, seasons_used=[s.label for s in past],
            mean_epidemic_weeks=r.mean_duration,
            quality_note=quality_issue(r.epidemic_threshold, r.medium, r.high,
                                       r.very_high, spec.metric),
        ))
    return out


def quality_issue(epi: float, medium: float, high: float, very_high: float,
                  metric: str = "positivity") -> str | None:
    """Why MEM levels (positivity in percent, or incidence) are not usable, or None. MEM
    output is unconstrained, so noisy or irregular series can give unordered or
    impossible levels."""
    if epi <= 0:
        return ("epidemic threshold is not above 0%" if metric == "positivity" else
                "epidemic threshold is not above 0 cases per 100,000")
    if not epi < medium < high < very_high:
        return ("levels are not ordered (epidemic threshold above an intensity level): "
                "past seasons too irregular for MEM")
    if metric == "positivity" and very_high >= 100:
        return "an intensity level is at or above 100% positivity: past values too extreme"
    return None


def compute_thresholds(weekly: pd.DataFrame, countries: pd.DataFrame, reference_week: date,
                       latest_week: date, spec: cfg.DetectionSpec = cfg.INFLUENZA
                       ) -> tuple[list[ThresholdRow], dict]:
    """Thresholds for every country with a season type. Also returns, per country, why
    the current season has none (for the UI's 'not assessed' reason)."""
    rows_out: list[ThresholdRow] = []
    not_assessed: dict[str, str] = {}
    meta = countries.set_index("iso3")
    column = "season_type" if "season_type" in meta else "flu_season"
    for iso3, rows in weekly.groupby("iso3", sort=True):
        season_type = meta.at[iso3, column] if iso3 in meta.index else None
        if not season_type:
            continue
        if season_type not in spec.mem_season_types:
            not_assessed[iso3] = ("year-round circulation: MEM assumes one epidemic per "
                                  "season")
            continue
        seasons = country_seasons(rows, season_type, reference_week, spec)
        current_year = int(season_start_year(pd.Series([pd.Timestamp(latest_week)]),
                                             pd.Series([season_type]))[0])
        got = thresholds_for_country(iso3, seasons, season_type, current_year, spec)
        rows_out += got
        if not got or got[-1].season_start != season_first_week(current_year, season_type):
            n = sum(s.usable for s in seasons if s.year < current_year)
            not_assessed[iso3] = (f"{n} usable past season{'s' if n != 1 else ''} "
                                  f"(needs {cfg.MIN_SEASONS_FOR_THRESHOLDS})")
        elif got[-1].quality_note:
            not_assessed[iso3] = f"MEM levels unusable: {got[-1].quality_note}"
    return rows_out, not_assessed
