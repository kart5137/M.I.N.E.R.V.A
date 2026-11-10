"""Endemic channel: each country's usual weekly range from its own past years (D5, dengue).

The method used in dengue surveillance in the Americas (Bortman 1999; PAHO), in its
quartile form. For calendar year Y and ISO week w of country c:

1. Candidate years are the latest CHANNEL_YEARS complete calendar years before Y with
   incidence in ≥ CHANNEL_MIN_COMPLETENESS of their ISO weeks.
2. The CHANNEL_EXCLUDE_TOP years with the highest mean incidence are left out (epidemic
   years do not belong in a baseline of usual activity); at least CHANNEL_MIN_YEARS must
   remain, otherwise c has no channel for Y.
3. The week's values are pooled from the same ISO week ±CHANNEL_WEEK_HALFWIDTH of every
   year used (week 53 uses week 52 in years without one); with ≥ CHANNEL_MIN_VALUES the
   median, 75th and 90th percentiles are the week's levels.

Zones: below the median, median to the 75th percentile (top of the channel), above the
channel, above the 90th percentile. Values are weekly incidence per 100,000.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ei_pipeline.detection import config as cfg

WEEK = timedelta(weeks=1)


@dataclass
class ChannelRow:
    iso3: str
    year: int
    iso_week: int
    week_start: date
    median: float
    q75: float
    p90: float
    n_values: int
    years_used: list[int]
    excluded_years: list[int]


@dataclass
class YearStat:
    year: int
    completeness: float
    mean: float
    complete: bool


def weeks_in(year: int) -> int:
    return date(year, 12, 28).isocalendar()[1]


def week_monday(year: int, week: int) -> date:
    """Monday of ISO week `week` of `year`; week 53 falls back to 52 when absent."""
    return date.fromisocalendar(year, min(week, weeks_in(year)), 1)


def year_stats(values: dict[date, float], years, reference_week: date) -> dict[int, YearStat]:
    out = {}
    for y in years:
        n = weeks_in(y)
        v = np.array([values.get(week_monday(y, w), np.nan) for w in range(1, n + 1)])
        ok = ~np.isnan(v)
        out[y] = YearStat(year=y, completeness=float(ok.mean()),
                          mean=float(v[ok].mean()) if ok.any() else np.nan,
                          complete=week_monday(y, n) <= reference_week)
    return out


def usable(s: YearStat) -> bool:
    return s.complete and s.completeness >= cfg.CHANNEL_MIN_COMPLETENESS


def years_for(stats: dict[int, YearStat], year: int) -> tuple[list[int], list[int]] | None:
    """(years used, years left out) for the channel of `year`, or None if too few."""
    cands = [y for y in range(year - cfg.CHANNEL_YEARS, year)
             if y in stats and usable(stats[y])]
    if len(cands) < cfg.CHANNEL_MIN_YEARS + cfg.CHANNEL_EXCLUDE_TOP:
        return None
    ranked = sorted(cands, key=lambda y: (-stats[y].mean, y))
    excluded = sorted(ranked[:cfg.CHANNEL_EXCLUDE_TOP])
    return [y for y in cands if y not in excluded], excluded


def channel_rows(iso3: str, values: dict[date, float], year: int, used: list[int],
                 excluded: list[int]) -> list[ChannelRow]:
    out = []
    h = cfg.CHANNEL_WEEK_HALFWIDTH
    for w in range(1, weeks_in(year) + 1):
        pooled = []
        for y in used:
            d = week_monday(y, w)
            pooled += [values[d + WEEK * k] for k in range(-h, h + 1)
                       if d + WEEK * k in values]
        if len(pooled) < cfg.CHANNEL_MIN_VALUES:
            continue
        med, q75, p90 = (float(x) for x in np.quantile(pooled, cfg.CHANNEL_QUANTILES))
        out.append(ChannelRow(iso3=iso3, year=year, iso_week=w,
                              week_start=date.fromisocalendar(year, w, 1), median=med,
                              q75=q75, p90=p90, n_values=len(pooled), years_used=used,
                              excluded_years=excluded))
    return out


def needed_years() -> int:
    return cfg.CHANNEL_MIN_YEARS + cfg.CHANNEL_EXCLUDE_TOP


def compute_channels(weekly: pd.DataFrame, reference_week: date, last_year: int
                     ) -> tuple[list[ChannelRow], dict[str, str]]:
    """Channels for CHANNEL_FROM_YEAR … `last_year`, and why a country has none for
    `last_year` (for the UI's 'not assessed' reason)."""
    rows: list[ChannelRow] = []
    reasons: dict[str, str] = {}
    first = cfg.CHANNEL_FROM_YEAR - cfg.CHANNEL_YEARS
    for iso3, g in weekly.groupby("iso3", sort=True):
        g = g[g["p"].notna()]
        values = dict(zip(g["week_start"].dt.date, g["p"].astype(float), strict=True))
        if not values:
            continue
        stats = year_stats(values, range(first, last_year), reference_week)
        for year in range(cfg.CHANNEL_FROM_YEAR, last_year + 1):
            got = years_for(stats, year)
            if got is not None:
                rows += channel_rows(str(iso3), values, year, *got)
        if years_for(stats, last_year) is None:
            n = sum(usable(s) for y, s in stats.items() if y >= last_year - cfg.CHANNEL_YEARS)
            reasons[str(iso3)] = (
                f"{n} complete reporting year{'s' if n != 1 else ''} in "
                f"{last_year - cfg.CHANNEL_YEARS}–{last_year - 1} (the endemic channel needs "
                f"{needed_years()}: the highest year is left out, ≥ {cfg.CHANNEL_MIN_YEARS} "
                f"remain)")
    return rows, reasons


def channel_check(weekly: pd.DataFrame, rows: list[ChannelRow], reference_week: date
                  ) -> dict[str, dict]:
    """Per completed calendar year: how many observed country-weeks were above the
    channel (75th percentile) and above the 90th percentile of their week. In a year like
    those the channel was built from, about 25% and 10% are expected."""
    if not rows:
        return {}
    ch = pd.DataFrame([(r.iso3, pd.Timestamp(r.week_start), r.year, r.q75, r.p90)
                       for r in rows], columns=["iso3", "week_start", "year", "q75", "p90"])
    obs = weekly.loc[weekly["p"].notna(), ["iso3", "week_start", "p"]]
    m = ch.merge(obs, on=["iso3", "week_start"])
    m = m[m["week_start"].dt.date <= reference_week]
    out = {}
    for year, g in m.groupby("year"):
        if week_monday(int(year), weeks_in(int(year))) > reference_week:
            continue
        out[str(int(year))] = {
            "countries": int(g["iso3"].nunique()), "country_weeks": len(g),
            "above_channel": round(float((g["p"] > g["q75"]).mean()), 3),
            "above_p90": round(float((g["p"] > g["p90"]).mean()), 3),
        }
    return out
