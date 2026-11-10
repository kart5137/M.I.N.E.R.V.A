"""Detection outputs written by `ei detect run` (pipeline/src/ei_pipeline/detection)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.queries.common import WEEK, DiseaseContext, Window
from app.schemas.detection import (
    AnomalyCountry,
    AnomalyItem,
    ChannelWeek,
    DetectionRunInfo,
    EndemicChannel,
    HistoryPoint,
    HotspotItem,
    HotspotStatus,
    LocalStat,
    NotAssessed,
    RiskItem,
    ThresholdLevels,
)

SEVERITY_RANK = {"moderate": 1, "high": 2, "severe": 3}
FDR_ALPHA = 0.05
PERMUTATIONS = 999
ANOMALY_NOTE = (
    "Seasonal EWMA: positivity above the 90th percentile of the same ISO week ±1 in the "
    "latest 5 non-COVID years, and an EWMA control chart (λ 0.3, L 3) on the standardised "
    "residual signals. Isolation Forest flags are a secondary signal and never trigger "
    "alerts."
)
DENGUE_ANOMALY_NOTE = (
    "Seasonal EWMA on weekly incidence: above the 90th percentile of the same ISO week ±1 "
    "in the latest 5 years (on the log scale, with one case per 100,000 added), and an EWMA "
    "control chart (λ 0.3, L 3) on the standardised residual signals. Comparable to the "
    "endemic channel used in dengue surveillance. Isolation Forest flags are a secondary "
    "signal and never trigger alerts."
)
RISK_RULE = (
    "Active 2-week-ahead forecast vs the season's Moving Epidemic Method levels: below the "
    "epidemic threshold = low; from the epidemic threshold up to high intensity = moderate; "
    "at or above high intensity = high."
)
DENGUE_RISK_RULE = (
    "Active 2-week-ahead incidence forecast vs the endemic channel of the target week (its "
    "usual range: the same ISO week ±1 in up to 7 earlier complete years, the highest year "
    "left out, at least 4 remaining): below the top of the channel (75th percentile) = low; "
    "up to the 90th percentile = moderate; at or above it = high. Both levels are at least "
    "one weekly case. Countries without 5 complete reporting years among the last 7 are "
    "not assessed."
)


def anomaly_note(ctx: DiseaseContext) -> str:
    return DENGUE_ANOMALY_NOTE if ctx.case_based else ANOMALY_NOTE


def risk_rule(ctx: DiseaseContext) -> str:
    return DENGUE_RISK_RULE if ctx.case_based else RISK_RULE
_REGION = "(CAST(:region AS text) IS NULL OR c.who_region = :region)"


def run_info(session: Session, ctx: DiseaseContext) -> tuple[DetectionRunInfo | None,
                                                               dict | None]:
    r = session.execute(text("""
        SELECT run_key, reference_week, finished_at, summary FROM detection_runs
        WHERE disease_id = :d AND finished_at IS NOT NULL
        ORDER BY finished_at DESC LIMIT 1
    """), {"d": ctx.id}).one_or_none()
    if r is None:
        return None, None
    return (DetectionRunInfo(run_key=r.run_key, reference_week=r.reference_week,
                             finished_at=r.finished_at), r.summary)


# --- Anomalies ----------------------------------------------------------------------------

_ANOMALIES = text(f"""
    SELECT a.iso3, c.name, c.who_region, a.week_start, a.method, a.observed, a.expected,
           a.upper_band, a.score, a.ewma, a.ewma_limit, a.specimens_tested, a.severity,
           a.is_provisional
    FROM anomalies a JOIN countries c ON c.iso3 = a.iso3
    WHERE a.disease_id = :d AND a.week_start BETWEEN :start AND :end AND {_REGION}
      AND (CAST(:iso3 AS text) IS NULL OR a.iso3 = :iso3)
      AND (CAST(:method AS text) IS NULL OR a.method = :method)
    ORDER BY a.week_start DESC, a.score DESC, a.iso3
""")


def anomalies(session: Session, ctx: DiseaseContext, w: Window, region: str | None,
              iso3: str | None, method: str | None) -> list[AnomalyItem]:
    rows = session.execute(_ANOMALIES, {"d": ctx.id, "start": w.start, "end": w.end,
                                        "region": region, "iso3": iso3,
                                        "method": method}).mappings()
    return [AnomalyItem(**r) for r in rows]


def by_country(items: list[AnomalyItem]) -> list[AnomalyCountry]:
    out: dict[str, AnomalyCountry] = {}
    for a in items:
        if a.method != "seasonal_ewma":
            continue
        cur = out.get(a.iso3)
        sev = a.severity or "moderate"
        if cur is None:
            out[a.iso3] = AnomalyCountry(iso3=a.iso3, weeks_flagged=1, latest_week=a.week_start,
                                         max_severity=sev, max_score=a.score)
            continue
        cur.weeks_flagged += 1
        cur.latest_week = max(cur.latest_week, a.week_start)
        cur.max_score = max(cur.max_score, a.score)
        if SEVERITY_RANK[sev] > SEVERITY_RANK[cur.max_severity]:
            cur.max_severity = sev
    return sorted(out.values(), key=lambda x: (-SEVERITY_RANK[x.max_severity], -x.max_score))


def anomaly_country_count(session: Session, ctx: DiseaseContext, w: Window,
                          region: str | None) -> int:
    return session.execute(text(f"""
        SELECT count(DISTINCT a.iso3) FROM anomalies a JOIN countries c ON c.iso3 = a.iso3
        WHERE a.disease_id = :d AND a.method = 'seasonal_ewma'
          AND a.week_start BETWEEN :start AND :end AND {_REGION}
    """), {"d": ctx.id, "start": w.start, "end": w.end, "region": region}).scalar_one()


# --- Hotspots -----------------------------------------------------------------------------

def hotspot_range(session: Session, ctx: DiseaseContext) -> tuple[date | None, date | None,
                                                                  int | None, str | None]:
    r = session.execute(text("""
        SELECT min(window_end), max(window_end), min(window_weeks), min(weights_spec)
        FROM hotspot_results WHERE disease_id = :d
    """), {"d": ctx.id}).one()
    return r[0], r[1], r[2], r[3]


def _stat(r, prefix: str) -> LocalStat:
    return LocalStat(stat_value=r[f"{prefix}_stat"], z_score=r[f"{prefix}_z"],
                     p_value=r[f"{prefix}_p"], p_fdr=r[f"{prefix}_fdr"],
                     classification=r[f"{prefix}_class"])


_PAIRS = """
    SELECT h.iso3, h.window_end, h.value, h.n_neighbours, h.neighbour_source,
      g.stat_value AS gi_stat, g.z_score AS gi_z, g.p_value AS gi_p, g.p_fdr AS gi_fdr,
      g.classification AS gi_class,
      m.stat_value AS lm_stat, m.z_score AS lm_z, m.p_value AS lm_p, m.p_fdr AS lm_fdr,
      m.classification AS lm_class, c.name, c.who_region
    FROM hotspot_results h
    JOIN hotspot_results g ON g.disease_id = h.disease_id AND g.iso3 = h.iso3
      AND g.window_end = h.window_end AND g.window_weeks = h.window_weeks
      AND g.statistic = 'gi_star'
    JOIN hotspot_results m ON m.disease_id = h.disease_id AND m.iso3 = h.iso3
      AND m.window_end = h.window_end AND m.window_weeks = h.window_weeks
      AND m.statistic = 'local_moran'
    JOIN countries c ON c.iso3 = h.iso3
    WHERE h.disease_id = :d AND h.statistic = 'gi_star'
"""


def hotspots(session: Session, ctx: DiseaseContext, window_end: date, region: str | None
             ) -> list[HotspotItem]:
    rows = session.execute(text(_PAIRS + f" AND h.window_end = :end AND {_REGION}"
                                " ORDER BY g.z_score DESC, h.iso3"),
                           {"d": ctx.id, "end": window_end, "region": region}).mappings()
    return [HotspotItem(iso3=r["iso3"], name=r["name"], who_region=r["who_region"],
                        value=r["value"], n_neighbours=r["n_neighbours"],
                        neighbour_source=r["neighbour_source"], gi_star=_stat(r, "gi"),
                        local_moran=_stat(r, "lm")) for r in rows]


def country_hotspots(session: Session, ctx: DiseaseContext, iso3: str) -> list[HotspotStatus]:
    rows = session.execute(text(_PAIRS + " AND h.iso3 = :iso3 ORDER BY h.window_end"),
                           {"d": ctx.id, "iso3": iso3}).mappings()
    return [HotspotStatus(window_end=r["window_end"], value=r["value"],
                          n_neighbours=r["n_neighbours"], neighbour_source=r["neighbour_source"],
                          gi_star=_stat(r, "gi"), local_moran=_stat(r, "lm")) for r in rows]


def hotspot_country_count(session: Session, ctx: DiseaseContext, window_end: date,
                          region: str | None) -> int | None:
    r = session.execute(text(f"""
        SELECT count(*) FILTER (WHERE h.classification = 'hot'), count(*)
        FROM hotspot_results h JOIN countries c ON c.iso3 = h.iso3
        WHERE h.disease_id = :d AND h.statistic = 'gi_star' AND h.window_end = :end
          AND {_REGION}
    """), {"d": ctx.id, "end": window_end, "region": region}).one()
    return r[0] if r[1] else None


def history(session: Session, ctx: DiseaseContext, region: str | None) -> list[HistoryPoint]:
    rows = session.execute(text(f"""
        WITH hs AS (
          SELECT h.window_end AS week_start,
            count(*) FILTER (WHERE h.classification = 'hot') AS hot,
            count(*) FILTER (WHERE h.classification = 'cold') AS cold,
            count(*) AS participants
          FROM hotspot_results h JOIN countries c ON c.iso3 = h.iso3
          WHERE h.disease_id = :d AND h.statistic = 'gi_star' AND {_REGION}
          GROUP BY h.window_end
        ), an AS (
          SELECT a.week_start, count(DISTINCT a.iso3) AS anomalies
          FROM anomalies a JOIN countries c ON c.iso3 = a.iso3
          WHERE a.disease_id = :d AND a.method = 'seasonal_ewma' AND {_REGION}
          GROUP BY a.week_start
        )
        SELECT hs.week_start, hs.hot, hs.cold, hs.participants,
               coalesce(an.anomalies, 0) AS anomalies
        FROM hs LEFT JOIN an USING (week_start) ORDER BY hs.week_start
    """), {"d": ctx.id, "region": region}).mappings()
    prov = ctx.provisional_from
    return [HistoryPoint(**r, is_provisional=prov is not None and r["week_start"] >= prov)
            for r in rows]


# --- Thresholds and risk ------------------------------------------------------------------

_THRESHOLD_COLS = """t.season, t.season_start, t.method, t.epidemic_threshold,
    t.post_threshold, t.medium, t.high, t.very_high, t.n_seasons_used, t.seasons_used,
    t.quality_note"""


def thresholds_by_season(session: Session, ctx: DiseaseContext, iso3: str
                         ) -> dict[date, ThresholdLevels]:
    rows = session.execute(text(f"""
        SELECT {_THRESHOLD_COLS} FROM seasonal_thresholds t
        WHERE t.disease_id = :d AND t.iso3 = :iso3 ORDER BY t.season_start
    """), {"d": ctx.id, "iso3": iso3}).mappings()
    return {r["season_start"]: ThresholdLevels(**r) for r in rows}


#: Risk rows are kept across runs (their history drives the escalation alert); current
#: levels are those of the disease's latest finished detection run. MEM rows also need
#: their thresholds (an earlier run's thresholds are replaced).
_LATEST_RUN = """(SELECT id FROM detection_runs WHERE disease_id = :d
                  AND finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1)"""
_CURRENT_RISK = f"""r.run_id = {_LATEST_RUN} AND (r.method <> 'mem' OR t.id IS NOT NULL)"""

_RISK = text(f"""
    SELECT r.iso3, c.name, c.who_region, r.assessed_week, r.target_week, r.risk_level, r.rule,
           r.forecast_point, r.forecast_lo80, r.forecast_hi80, r.model_type,
           r.method AS risk_method, r.season AS risk_season,
           r.epidemic_threshold AS risk_epidemic, r.high_threshold AS risk_high,
           t.id AS threshold_id, {_THRESHOLD_COLS}
    FROM risk_assessments r
    LEFT JOIN seasonal_thresholds t ON t.id = r.threshold_id
    JOIN countries c ON c.iso3 = r.iso3
    WHERE r.disease_id = :d AND {_CURRENT_RISK} AND {_REGION}
      AND (CAST(:iso3 AS text) IS NULL OR r.iso3 = :iso3)
    ORDER BY CASE r.risk_level WHEN 'high' THEN 0 WHEN 'moderate' THEN 1 ELSE 2 END,
             r.forecast_point / NULLIF(coalesce(t.epidemic_threshold, r.epidemic_threshold), 0)
             DESC, r.iso3
""")

_RISK_FIELDS = ("iso3", "name", "who_region", "assessed_week", "target_week", "risk_level",
                "rule", "forecast_point", "forecast_lo80", "forecast_hi80", "model_type")


def risk(session: Session, ctx: DiseaseContext, region: str | None,
         iso3: str | None = None) -> list[RiskItem]:
    rows = session.execute(_RISK, {"d": ctx.id, "region": region, "iso3": iso3}).mappings()
    out = []
    for r in rows:
        th = (ThresholdLevels(**{k: r[k] for k in ThresholdLevels.model_fields})
              if r["threshold_id"] is not None else None)
        out.append(RiskItem(
            **{k: r[k] for k in _RISK_FIELDS}, method=r["risk_method"],
            epidemic_threshold=th.epidemic_threshold if th else r["risk_epidemic"],
            high_threshold=th.high if th else r["risk_high"],
            season=th.season if th else r["risk_season"], thresholds=th))
    return out


def channel(session: Session, ctx: DiseaseContext, iso3: str) -> EndemicChannel | None:
    """The latest year's endemic channel of a country, if it has one."""
    rows = session.execute(text("""
        SELECT year, iso_week, week_start, median, q75, p90, years_used, excluded_years
        FROM endemic_channels
        WHERE disease_id = :d AND iso3 = :iso3
          AND year = (SELECT max(year) FROM endemic_channels
                      WHERE disease_id = :d AND iso3 = :iso3)
        ORDER BY iso_week
    """), {"d": ctx.id, "iso3": iso3}).mappings().all()
    if not rows:
        return None
    first = rows[0]
    return EndemicChannel(
        year=first["year"], years_used=first["years_used"],
        excluded_years=first["excluded_years"],
        weeks=[ChannelWeek(iso_week=r["iso_week"], week_start=r["week_start"],
                           median=r["median"], q75=r["q75"], p90=r["p90"]) for r in rows])


def not_assessed(session: Session, summary: dict | None, region: str | None,
                 assessed: set[str], ctx: DiseaseContext | None = None) -> list[NotAssessed]:
    reasons: dict[str, str] = dict((summary or {}).get("thresholds", {}).get("not_assessed", {}))
    # Countries in scope (influenza: a FluNet season type; dengue: weekly reporting) that
    # were not assessed, e.g. usable thresholds but no forecast this week.
    scope = ("EXISTS (SELECT 1 FROM surveillance_weekly s WHERE s.disease_id = :d "
             "AND s.iso3 = c.iso3)" if ctx is not None and ctx.case_based
             else "c.flu_season IS NOT NULL")
    rows = session.execute(text(f"""
        SELECT c.iso3, c.name FROM countries c
        WHERE {scope} AND {_REGION} ORDER BY c.name
    """), {"region": region, "d": ctx.id if ctx is not None else None}).all()
    fallback = ("no forecast this week (forecasts need a weekly Tier A/B series with "
                "population and cases in the reference week)"
                if ctx is not None and ctx.case_based else
                "no forecast this week (forecasts need a Tier A/B series with a value in "
                "the reference week)")
    return [NotAssessed(iso3=iso3, name=name, reason=reasons.get(iso3, fallback))
            for iso3, name in rows if iso3 not in assessed]


def above_threshold_count(session: Session, ctx: DiseaseContext, region: str | None
                          ) -> tuple[int, int]:
    r = session.execute(text(f"""
        SELECT count(*) FILTER (WHERE r.risk_level <> 'low'), count(*)
        FROM risk_assessments r JOIN countries c ON c.iso3 = r.iso3
        LEFT JOIN seasonal_thresholds t ON t.id = r.threshold_id
        WHERE r.disease_id = :d AND {_CURRENT_RISK} AND {_REGION}
    """), {"d": ctx.id, "region": region}).one()
    return r[0], r[1]


def last_weeks(ctx: DiseaseContext, n: int) -> Window:
    return Window(ctx.latest_week - WEEK * (n - 1), ctx.latest_week, n)
