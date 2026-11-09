"""Season alignment for one country.

Season types come from FluNet (`countries.flu_season`):
- **NH**: a season runs from ISO week 40 to ISO week 39 of the next year ("2025/26").
- **SH** and **YR** (year-round, mostly tropical): the calendar ISO year ("2026").

Each season is a list of weeks indexed from its first week, so curves from different
years overlay on the same x-axis. Peaks use only weeks with enough specimens.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.queries.common import (
    COVID_END,
    COVID_START,
    MIN_SPECIMENS_FOR_RATE,
    WEEK,
    DiseaseContext,
)
from app.queries.detection import thresholds_by_season
from app.schemas.countries import Season, SeasonPoint

NH_START_WEEK = 40


def season_of(week_start: date, season_type: str) -> tuple[int, str, date]:
    """(start year, label, first Monday) of the season containing `week_start`."""
    iso_year, iso_week, _ = week_start.isocalendar()
    if season_type == "NH":
        y = iso_year if iso_week >= NH_START_WEEK else iso_year - 1
        return y, f"{y}/{(y + 1) % 100:02d}", date.fromisocalendar(y, NH_START_WEEK, 1)
    return iso_year, str(iso_year), date.fromisocalendar(iso_year, 1, 1)


def season_bounds(start_year: int, season_type: str) -> tuple[date, date]:
    """First and last Monday of a season (52 or 53 weeks, following ISO years)."""
    week = NH_START_WEEK if season_type == "NH" else 1
    first = date.fromisocalendar(start_year, week, 1)
    return first, date.fromisocalendar(start_year + 1, week, 1) - WEEK


def build_seasons(rows, season_type: str, ctx: DiseaseContext, n: int) -> list[Season]:
    """Group weekly rows (week_start, tests, positives, positivity, provisional) into the
    latest `n` seasons up to the latest week, on a complete weekly calendar."""
    latest_year = season_of(ctx.latest_week, season_type)[0]
    first_year = max(season_of(ctx.first_week, season_type)[0], latest_year - n + 1)
    by_week = {r.week_start: r for r in rows}

    seasons: list[Season] = []
    for y in range(first_year, latest_year + 1):
        start, end = season_bounds(y, season_type)
        points: list[SeasonPoint] = []
        wk, i = start, 0
        while wk <= min(end, ctx.latest_week):
            r = by_week.get(wk)
            tests = r.specimens_tested if r else None
            points.append(SeasonPoint(
                index=i, week_start=wk, iso_week=wk.isocalendar()[1],
                reported=bool(tests and tests > 0),
                specimens_tested=tests, positives=r.positives if r else None,
                positivity=r.positivity if r else None,
                is_provisional=(ctx.provisional_from is not None
                                and wk >= ctx.provisional_from),
            ))
            wk, i = wk + WEEK, i + 1

        # Peak: settled weeks with enough specimens only.
        rated = [p for p in points if p.positivity is not None and not p.is_provisional
                 and (p.specimens_tested or 0) >= MIN_SPECIMENS_FOR_RATE]
        peak = max(rated, key=lambda p: p.positivity, default=None)
        reported = [p for p in points if p.reported]
        seasons.append(Season(
            label=season_of(start, season_type)[1], start=start, end=end,
            is_current=start <= ctx.latest_week <= end,
            covid_disrupted=start <= COVID_END and end >= COVID_START,
            weeks_reported=len(reported),
            positives=sum(p.positives or 0 for p in points) if reported else None,
            specimens_tested=sum(p.specimens_tested or 0 for p in reported) if reported else None,
            peak_positivity=peak.positivity if peak else None,
            peak_week=peak.week_start if peak else None,
            points=points,
        ))
    return seasons


def country_seasons(session: Session, ctx: DiseaseContext, iso3: str, season_type: str,
                    n: int) -> list[Season]:
    rows = session.execute(text("""
        SELECT week_start, specimens_tested, positives, positivity
        FROM surveillance_weekly WHERE disease_id = :d AND iso3 = :iso3
        ORDER BY week_start
    """), {"d": ctx.id, "iso3": iso3}).all()
    seasons = build_seasons(rows, season_type, ctx, n)
    levels = thresholds_by_season(session, ctx, iso3)
    for s in seasons:
        s.thresholds = levels.get(s.start)
    return seasons

