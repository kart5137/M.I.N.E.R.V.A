"""Shared context for surveillance queries: disease lookup, data-availability dates and
time windows.

Aggregation rules (used by every endpoint, documented in docs/DESIGN.md §5):

- **Detections** = sum of `positives` over all rows in the window.
- **Positivity** = sum(positives) / sum(specimens_tested), pooled over rows whose own
  positivity is valid (tests > 0 and positives ≤ tests). Not a mean of country rates.
- A country-week is **reported** when specimens_tested > 0.

Case-based diseases (dengue) have their own rules in app/queries/cases.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.schemas.common import ResponseMeta, SourceRef, WindowInfo

WEEK = timedelta(weeks=1)
WHO_REGIONS = ("AFR", "AMR", "EMR", "EUR", "SEAR", "WPR")
#: Below this many specimens a weekly or window positivity is too noisy to rank or peak on.
MIN_SPECIMENS_FOR_RATE = 10
#: COVID-19 disruption of influenza circulation and testing (DESIGN.md §2).
COVID_START, COVID_END = date(2020, 3, 1), date(2022, 6, 30)


@dataclass(frozen=True)
class DiseaseContext:
    id: int
    key: str
    name: str
    metric_label: str
    primary_metric: str
    first_week: date
    latest_week: date
    reference_week: date
    provisional_from: date | None
    sources: tuple[SourceRef, ...]

    @property
    def case_based(self) -> bool:
        """Reported case counts (dengue) rather than laboratory tests (influenza)."""
        return self.primary_metric == "cases"

    def meta(self) -> ResponseMeta:
        return ResponseMeta(
            disease=self.key,
            first_week=self.first_week,
            reference_week=self.reference_week,
            provisional_from=self.provisional_from,
            latest_week=self.latest_week,
            sources=list(self.sources),
        )


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    weeks: int

    @property
    def previous(self) -> Window:
        shift = WEEK * self.weeks
        return Window(self.start - shift, self.end - shift, self.weeks)

    def info(self, ctx: DiseaseContext) -> WindowInfo:
        provisional = ctx.provisional_from is not None and self.end >= ctx.provisional_from
        return WindowInfo(start=self.start, end=self.end, weeks=self.weeks,
                          includes_provisional=provisional)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def load_disease(session: Session, key: str) -> DiseaseContext:
    row = session.execute(
        text("""
            SELECT d.id, d.key, d.name, d.metric_label, d.primary_metric,
              d.native_granularity,
              (SELECT min(week_start) FROM surveillance_weekly WHERE disease_id = d.id),
              (SELECT max(week_start) FROM surveillance_weekly WHERE disease_id = d.id),
              (SELECT week_start FROM surveillance_weekly
                WHERE disease_id = d.id AND NOT is_provisional
                ORDER BY week_start DESC LIMIT 1),
              (SELECT week_start FROM surveillance_weekly
                WHERE disease_id = d.id AND is_provisional
                ORDER BY week_start LIMIT 1)
            FROM diseases d WHERE d.key = :key
        """),
        {"key": key},
    ).one_or_none()
    if row is None:
        raise ApiError(404, "unknown_disease", f"Unknown disease '{key}'.")
    did, dkey, name, label, metric, grain, first, latest, reference, provisional = row
    if grain == "annual":
        raise ApiError(422, "not_available",
                       f"{name} is reported yearly, so weekly views do not apply; use the "
                       "/annual endpoints (yearly estimates and reported cases).")
    if latest is None:
        raise ApiError(404, "no_data",
                       f"No surveillance data is loaded for {name}. Run `ei ingest all`.")

    sources = session.execute(
        text("""
            SELECT key, name, attribution_text FROM data_sources
            WHERE id IN (SELECT source_id FROM surveillance_weekly WHERE disease_id = :d
                         UNION SELECT source_id FROM surveillance_monthly WHERE disease_id = :d)
            ORDER BY key
        """),
        {"d": did},
    ).all()
    return DiseaseContext(
        id=did, key=dkey, name=name, metric_label=label, primary_metric=metric,
        first_week=first, latest_week=latest,
        # With only provisional rows there is no settled week yet; fall back to latest.
        reference_week=reference or latest,
        provisional_from=provisional,
        sources=tuple(SourceRef(key=k, name=n, attribution=a) for k, n, a in sources),
    )


def make_window(ctx: DiseaseContext, end: date | None, weeks: int) -> Window:
    """Window of `weeks` ISO weeks ending at `end` (default: the reference week)."""
    last = monday(end) if end else ctx.reference_week
    if not ctx.first_week <= last <= ctx.latest_week:
        raise ApiError(
            422, "out_of_range",
            f"'to' must be between {ctx.first_week} and {ctx.latest_week}.",
        )
    return Window(last - WEEK * (weeks - 1), last, weeks)


def check_region(region: str | None) -> str | None:
    if region is None:
        return None
    region = region.upper()
    if region not in WHO_REGIONS:
        raise ApiError(422, "invalid_region",
                       f"region must be one of {', '.join(WHO_REGIONS)}.")
    return region
