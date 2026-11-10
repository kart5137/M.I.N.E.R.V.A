"""Alert rules over stored detection outputs (DESIGN.md §6.6).

Rules (all deterministic; weeks from ALERTS_FROM to the latest week):

- **new_anomaly** — the first week of a seasonal-EWMA anomaly episode (an anomaly in week
  t and none in t − 1). Severity from the anomaly: moderate → low, high → medium,
  severe → high.
- **new_hotspot** — a country enters a Gi* hot spot (FDR < 0.05) in the 4-week window
  ending in week t and was not one in the window ending t − 1. Severity medium.
- **risk_escalation** — the risk level of the 2-week forecast is moderate or high and
  either it is the country's first assessment or the previous assessment was lower.
  Severity: moderate → medium, high → high.
- **sustained_growth** — weekly positivity rose in each of 3 consecutive weeks (4 weekly
  values in a row, each with ≥ 50 specimens) by ≥ 5 percentage points in total; alert in
  the first week the condition holds. Severity medium when the rise is ≥ 10 pp, else low.

Alerts are upserted on (disease, country, type, week). Active alerts that a run no longer
produces are marked `retracted`.

Dengue (D4) uses the same four rules on weekly incidence per 100,000, except
**sustained_growth**: incidence rose in each of 3 consecutive weeks (each week with
≥ 20 reported cases) by ≥ 50% in total; severity medium when it at least doubled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ei_db.models import Alert

ALERTS_FROM = date(2025, 1, 6)
GROWTH_WEEKS = 3
GROWTH_MIN_PP = 5.0
GROWTH_MEDIUM_PP = 10.0
GROWTH_MIN_TESTS = 50
#: Dengue growth rule (relative rise; each week needs this many reported cases).
DENGUE_GROWTH_MIN_RISE = 0.50
DENGUE_GROWTH_MEDIUM_RISE = 1.00
DENGUE_GROWTH_MIN_CASES = 20
WEEK = timedelta(weeks=1)

ANOMALY_SEVERITY = {"moderate": "low", "high": "medium", "severe": "high"}
RISK_SEVERITY = {"moderate": "medium", "high": "high"}
RISK_RANK = {"low": 0, "moderate": 1, "high": 2}

RULES = {
    "new_anomaly": "First week of a seasonal-EWMA anomaly episode (none the week before).",
    "new_hotspot": "Enters a Gi* hot spot (FDR < 0.05) in the 4-week window ending this "
                   "week; not one the week before.",
    "risk_escalation": "2-week forecast at moderate or high risk, first assessment or up "
                       "from the previous one.",
    "sustained_growth": f"Positivity up in {GROWTH_WEEKS} consecutive weeks by "
                        f"≥ {GROWTH_MIN_PP:g} pp in total (≥ {GROWTH_MIN_TESTS} specimens "
                        "each week).",
}
DENGUE_GROWTH_RULE = (f"Incidence up in {GROWTH_WEEKS} consecutive weeks by "
                      f"≥ {DENGUE_GROWTH_MIN_RISE:.0%} in total (≥ {DENGUE_GROWTH_MIN_CASES} "
                      "reported cases each week).")


def rules(metric: str = "positivity") -> dict[str, str]:
    if metric == "positivity":
        return RULES
    return {k: v.replace("positivity", "incidence").replace("Positivity", "Incidence")
            for k, v in RULES.items()} | {"sustained_growth": DENGUE_GROWTH_RULE}


@dataclass
class AlertRow:
    iso3: str
    alert_type: str
    severity: str
    week_start: date
    title: str
    details: dict = field(default_factory=dict)
    anomaly_id: int | None = None
    hotspot_id: int | None = None
    risk_id: int | None = None


def _pct(v: float | None) -> str:
    return "—" if v is None or pd.isna(v) else f"{v * 100:.1f}%"


def _inc(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    d = 2 if abs(v) < 10 else 1 if abs(v) < 100 else 0
    return f"{v:,.{d}f} per 100k"


def _fmt(metric: str):
    return _pct if metric == "positivity" else _inc


def _r(v) -> float | None:
    return None if v is None or pd.isna(v) else round(float(v), 6)


def anomaly_alerts(df: pd.DataFrame, metric: str = "positivity") -> list[AlertRow]:
    """`df`: seasonal-EWMA anomalies (id, iso3, name, week_start, observed, expected,
    upper_band, score, severity, is_provisional, specimens_tested)."""
    f, out = _fmt(metric), []
    for _, g in df.sort_values(["iso3", "week_start"]).groupby("iso3"):
        weeks = set(g["week_start"])
        for r in g.itertuples():
            if r.week_start - WEEK in weeks or r.week_start < ALERTS_FROM:
                continue
            out.append(AlertRow(
                iso3=r.iso3, alert_type="new_anomaly", week_start=r.week_start,
                severity=ANOMALY_SEVERITY[r.severity],
                title=(f"{r.name}: {metric} {f(r.observed)} above the seasonal range "
                       f"(expected {f(r.expected)}, upper band {f(r.upper_band)})"),
                details={"metric": metric, "observed": _r(r.observed),
                         "expected": _r(r.expected),
                         "upper_band": _r(r.upper_band), "score": _r(r.score),
                         "anomaly_severity": r.severity,
                         "specimens_tested": None if pd.isna(r.specimens_tested)
                         else int(r.specimens_tested),
                         "provisional": bool(r.is_provisional),
                         "rule": rules(metric)["new_anomaly"]},
                anomaly_id=int(r.id),
            ))
    return out


def hotspot_alerts(df: pd.DataFrame, metric: str = "positivity") -> list[AlertRow]:
    """`df`: Gi* rows (id, iso3, name, window_end, value, z_score, p_fdr, classification)."""
    f = _fmt(metric)
    hot = df[df["classification"] == "hot"]
    keys = set(zip(hot["iso3"], hot["window_end"], strict=True))
    out = []
    for r in hot.sort_values(["iso3", "window_end"]).itertuples():
        if (r.iso3, r.window_end - WEEK) in keys or r.window_end < ALERTS_FROM:
            continue
        out.append(AlertRow(
            iso3=r.iso3, alert_type="new_hotspot", week_start=r.window_end, severity="medium",
            title=(f"{r.name}: new Gi* hot spot (4-week {metric} {f(r.value)}, "
                   f"z {r.z_score:+.2f}, FDR p {r.p_fdr:.3f})"),
            details={"metric": metric, "value": _r(r.value), "z_score": _r(r.z_score),
                     "p_fdr": _r(r.p_fdr), "window_weeks": 4,
                     "rule": rules(metric)["new_hotspot"]},
            hotspot_id=int(r.id),
        ))
    return out


def risk_alerts(df: pd.DataFrame, metric: str = "positivity") -> list[AlertRow]:
    """`df`: all stored risk assessments (id, iso3, name, assessed_week, target_week,
    risk_level, forecast_point, epidemic_threshold, high_threshold, season)."""
    f, out = _fmt(metric), []
    for _, g in df.sort_values(["iso3", "assessed_week"]).groupby("iso3"):
        prev = None
        for r in g.itertuples():
            rank = RISK_RANK[r.risk_level]
            if (r.risk_level != "low" and (prev is None or rank > RISK_RANK[prev])
                    and r.assessed_week >= ALERTS_FROM):
                out.append(AlertRow(
                    iso3=r.iso3, alert_type="risk_escalation", week_start=r.assessed_week,
                    severity=RISK_SEVERITY[r.risk_level],
                    title=(f"{r.name}: {r.risk_level} risk — 2-week forecast "
                           f"{f(r.forecast_point)} vs epidemic threshold "
                           f"{f(r.epidemic_threshold)}"),
                    details={"metric": metric, "risk_level": r.risk_level,
                             "previous_level": prev,
                             "target_week": r.target_week.isoformat(),
                             "forecast_point": _r(r.forecast_point),
                             "epidemic_threshold": _r(r.epidemic_threshold),
                             "high_threshold": _r(r.high_threshold), "season": r.season,
                             "rule": rules(metric)["risk_escalation"]},
                    risk_id=int(r.id),
                ))
            prev = r.risk_level
    return out


def growth_alerts(df: pd.DataFrame) -> list[AlertRow]:
    """`df`: weekly rows (iso3, name, week_start, tests, positives, is_provisional)."""
    out = []
    ok = df[(df["tests"] >= GROWTH_MIN_TESTS) & (df["positives"] <= df["tests"])].copy()
    ok["p"] = ok["positives"] / ok["tests"]
    for iso3, g in ok.sort_values(["iso3", "week_start"]).groupby("iso3"):
        weeks, p = list(g["week_start"]), list(g["p"])
        prov, name = list(g["is_provisional"]), g["name"].iloc[0]
        holding = False
        for i in range(len(weeks)):
            cond = False
            if i >= GROWTH_WEEKS:
                span = weeks[i - GROWTH_WEEKS: i + 1]
                vals = p[i - GROWTH_WEEKS: i + 1]
                consecutive = all(b - a == WEEK for a, b in zip(span, span[1:], strict=False))
                rising = all(b > a for a, b in zip(vals, vals[1:], strict=False))
                rise_pp = (vals[-1] - vals[0]) * 100
                cond = consecutive and rising and rise_pp >= GROWTH_MIN_PP
            if cond and not holding and weeks[i] >= ALERTS_FROM:
                out.append(AlertRow(
                    iso3=iso3, alert_type="sustained_growth", week_start=weeks[i],
                    severity="medium" if rise_pp >= GROWTH_MEDIUM_PP else "low",
                    title=(f"{name}: positivity up {GROWTH_WEEKS} weeks in a row, "
                           f"{_pct(vals[0])} → {_pct(vals[-1])} (+{rise_pp:.1f} pp)"),
                    details={"from_week": span[0].isoformat(), "values": [_r(v) for v in vals],
                             "rise_pp": round(rise_pp, 3), "provisional": bool(prov[i]),
                             "rule": RULES["sustained_growth"]},
                ))
            holding = cond
    return out


def dengue_growth_alerts(df: pd.DataFrame) -> list[AlertRow]:
    """`df`: weekly rows (iso3, name, week_start, cases, population, is_provisional)."""
    out = []
    ok = df[(df["cases"] >= DENGUE_GROWTH_MIN_CASES) & (df["population"] > 0)].copy()
    ok["p"] = ok["cases"] / ok["population"] * 1e5
    for iso3, g in ok.sort_values(["iso3", "week_start"]).groupby("iso3"):
        weeks, p = list(g["week_start"]), list(g["p"])
        prov, name = list(g["is_provisional"]), g["name"].iloc[0]
        holding = False
        for i in range(len(weeks)):
            cond = False
            if i >= GROWTH_WEEKS:
                span = weeks[i - GROWTH_WEEKS: i + 1]
                vals = p[i - GROWTH_WEEKS: i + 1]
                consecutive = all(b - a == WEEK for a, b in zip(span, span[1:], strict=False))
                rising = all(b > a for a, b in zip(vals, vals[1:], strict=False))
                rise = vals[-1] / vals[0] - 1
                cond = consecutive and rising and rise >= DENGUE_GROWTH_MIN_RISE
            if cond and not holding and weeks[i] >= ALERTS_FROM:
                out.append(AlertRow(
                    iso3=iso3, alert_type="sustained_growth", week_start=weeks[i],
                    severity="medium" if rise >= DENGUE_GROWTH_MEDIUM_RISE else "low",
                    title=(f"{name}: incidence up {GROWTH_WEEKS} weeks in a row, "
                           f"{_inc(vals[0])} → {_inc(vals[-1])} (+{rise:.0%})"),
                    details={"metric": "incidence", "from_week": span[0].isoformat(),
                             "values": [_r(v) for v in vals], "rise_pct": round(rise * 100, 1),
                             "provisional": bool(prov[i]), "rule": DENGUE_GROWTH_RULE},
                ))
            holding = cond
    return out


def _load(engine: Engine, disease_id: int, metric: str = "positivity"
          ) -> dict[str, pd.DataFrame]:
    with engine.connect() as c:
        q = lambda sql: pd.read_sql(text(sql), c, params={"d": disease_id})  # noqa: E731
        frames = {
            "anomalies": q("""
                SELECT a.id, a.iso3, c.name, a.week_start, a.observed, a.expected,
                       a.upper_band, a.score, a.severity, a.is_provisional, a.specimens_tested
                FROM anomalies a JOIN countries c ON c.iso3 = a.iso3
                WHERE a.disease_id = :d AND a.method = 'seasonal_ewma'"""),
            "hotspots": q("""
                SELECT h.id, h.iso3, c.name, h.window_end, h.value, h.z_score, h.p_fdr,
                       h.classification
                FROM hotspot_results h JOIN countries c ON c.iso3 = h.iso3
                WHERE h.disease_id = :d AND h.statistic = 'gi_star'"""),
            "risk": q("""
                SELECT r.id, r.iso3, c.name, r.assessed_week, r.target_week, r.risk_level,
                       r.forecast_point, r.epidemic_threshold, r.high_threshold, r.season
                FROM risk_assessments r JOIN countries c ON c.iso3 = r.iso3
                WHERE r.disease_id = :d"""),
            "weekly": q(f"""
                SELECT s.iso3, c.name, s.week_start, s.specimens_tested AS tests,
                       s.positives, s.is_provisional
                FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
                WHERE s.disease_id = :d AND s.week_start >= DATE '{ALERTS_FROM}' - 28
                  AND s.positives IS NOT NULL AND s.specimens_tested > 0""")
            if metric == "positivity" else q(f"""
                SELECT s.iso3, c.name, s.week_start, s.cases, s.is_provisional,
                  (SELECT pa.population::float8 FROM population_annual pa
                    WHERE pa.iso3 = s.iso3 AND pa.population > 0
                    ORDER BY (pa.year <= extract(year FROM s.week_start)) DESC,
                             CASE WHEN pa.year <= extract(year FROM s.week_start)
                                  THEN -pa.year ELSE pa.year END
                    LIMIT 1) AS population
                FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
                WHERE s.disease_id = :d AND s.week_start >= DATE '{ALERTS_FROM}' - 28
                  AND s.cases IS NOT NULL"""),
        }
    for f, cols in (("anomalies", ["week_start"]), ("hotspots", ["window_end"]),
                    ("risk", ["assessed_week", "target_week"]), ("weekly", ["week_start"])):
        for col in cols:
            frames[f][col] = pd.to_datetime(frames[f][col]).dt.date
    return frames


def build_alerts(frames: dict[str, pd.DataFrame], metric: str = "positivity"
                 ) -> list[AlertRow]:
    growth = (growth_alerts(frames["weekly"]) if metric == "positivity"
              else dengue_growth_alerts(frames["weekly"]))
    return (anomaly_alerts(frames["anomalies"], metric)
            + hotspot_alerts(frames["hotspots"], metric)
            + risk_alerts(frames["risk"], metric) + growth)


def generate_alerts(engine: Engine, disease_id: int, run_id: int,
                    metric: str = "positivity") -> dict:
    alerts = build_alerts(_load(engine, disease_id, metric), metric)
    with engine.begin() as c:
        for a in alerts:
            values = {
                "disease_id": disease_id, "iso3": a.iso3, "alert_type": a.alert_type,
                "severity": a.severity, "week_start": a.week_start, "title": a.title,
                "details": a.details, "status": "active", "anomaly_id": a.anomaly_id,
                "hotspot_id": a.hotspot_id, "risk_id": a.risk_id, "first_run_id": run_id,
                "last_run_id": run_id,
            }
            stmt = pg_insert(Alert).values(**values)
            c.execute(stmt.on_conflict_do_update(
                index_elements=["disease_id", "iso3", "alert_type", "week_start"],
                set_={k: stmt.excluded[k] for k in (
                    "severity", "title", "details", "status", "anomaly_id", "hotspot_id",
                    "risk_id", "last_run_id")} | {"updated_at": text("now()"),
                                                  "retracted_at": None},
            ))
        retracted = c.execute(text("""
            UPDATE alerts SET status = 'retracted', retracted_at = now(), updated_at = now()
            WHERE disease_id = :d AND status = 'active'
              AND (last_run_id IS NULL OR last_run_id <> :run)
        """), {"d": disease_id, "run": run_id}).rowcount
    counts: dict[str, int] = {}
    for a in alerts:
        counts[a.alert_type] = counts.get(a.alert_type, 0) + 1
    return {"active": len(alerts), "by_type": counts, "retracted_now": retracted}
