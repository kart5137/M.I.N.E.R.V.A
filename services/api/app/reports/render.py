"""Render a report's facts as Markdown. Pure function of the facts: no clock, no
database, no locale, so the same facts always give the same bytes."""

from __future__ import annotations

from datetime import date

from app.reports.facts import MONTHS, title_of

ALERT_LABELS = {
    "new_anomaly": "New anomaly",
    "new_hotspot": "New hot spot",
    "risk_escalation": "Risk escalation",
    "sustained_growth": "Sustained growth",
}
GI = {"hot": "hot spot", "cold": "cold spot", "ns": "not significant"}
MORAN = {"HH": "high–high cluster", "LL": "low–low cluster", "HL": "high outlier",
         "LH": "low outlier", "ns": "not significant"}


def _d(iso: str | None) -> str:
    if not iso:
        return "—"
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _month(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1]} {d.year}"


def _pct(v: float | None, digits: int = 1) -> str:
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def _int(v: float | None) -> str:
    return "—" if v is None else f"{round(v):,}"


def _pp(cur: float | None, prev: float | None) -> str:
    if cur is None or prev is None:
        return "no comparison"
    diff = (cur - prev) * 100
    return f"{diff:+.1f} pp vs {_pct(prev)}"


def _rel(cur: float | None, prev: float | None) -> str:
    if cur is None or not prev:
        return "no comparison"
    return f"{(cur - prev) / prev * 100:+.1f}% vs {_int(prev)}"


def _inc(v: float | None, digits: int | None = None) -> str:
    """Incidence per 100,000 (dengue): 2 decimals below 10, 1 below 100, else none."""
    if v is None:
        return "—"
    d = digits if digits is not None else (2 if abs(v) < 10 else 1 if abs(v) < 100 else 0)
    return f"{v:,.{d}f}"


def _rel_inc(cur: float | None, prev: float | None) -> str:
    if cur is None or not prev:
        return "no comparison"
    return f"{(cur - prev) / prev * 100:+.1f}% vs {_inc(prev)}"


def _table(head: list[str], rows: list[list[str]], align: str) -> list[str]:
    sep = ["---:" if a == "r" else "---" for a in align]
    return (["| " + " | ".join(head) + " |", "| " + " | ".join(sep) + " |"]
            + ["| " + " | ".join(r) + " |" for r in rows])


def render_markdown(c: dict) -> str:
    p = c["period"]
    lines = [f"# {title_of(c)}", ""]
    lines.append(f"Period: {_d(p['start'])} – {_d(p['end'])} ({p['weeks']} ISO weeks), "
                 f"compared with {_d(p['previous_start'])} – {_d(p['previous_end'])}.")
    if p["includes_provisional"]:
        lines.append("")
        lines.append(f"> The period includes provisional weeks (from "
                     f"{_d(c['data']['provisional_from'])}); values will change as "
                     "countries finish reporting.")
    lines.append("")

    s = c["summary"]
    inc = c.get("metric") == "incidence"
    v = _inc if inc else _pct          # value formatter (incidence per 100k or positivity)
    unit = " per 100,000" if inc else ""
    lines += ["## Summary", ""]
    if inc:
        lines += _dengue_summary(c, s, p)
    elif c["scope"] == "global":
        lines += [
            f"- Lab-confirmed detections: **{_int(s['detections'])}** "
            f"({_rel(s['detections'], s['detections_previous'])}).",
            f"- Test positivity: **{_pct(s['positivity'])}** "
            f"({_pp(s['positivity'], s['positivity_previous'])}).",
            f"- Countries reporting: **{_int(s['countries_reporting'])}** "
            f"(previously {_int(s['countries_reporting_previous'])}).",
        ]
        if s["countries_with_anomaly"] is not None:
            lines += [
                f"- Countries with an anomaly: **{_int(s['countries_with_anomaly'])}**.",
                f"- Countries in a Gi* hot spot (4 weeks to the period end): "
                f"**{_int(s['countries_in_hotspot'])}**.",
                f"- Latest 2-week forecast at or above the epidemic threshold: "
                f"**{_int(s['above_threshold'])}** of {_int(s['risk_assessed'])} countries "
                "with thresholds.",
            ]
    else:
        if s["weeks_reported"] == 0:
            lines.append("- No influenza testing was reported in this period.")
        else:
            lines += [
                f"- Test positivity: **{_pct(s['positivity'])}** "
                f"({_pp(s['positivity'], s['positivity_previous'])}).",
                f"- Lab-confirmed detections: **{_int(s['detections'])}** from "
                f"{_int(s['specimens_tested'])} specimens "
                f"({_rel(s['detections'], s['detections_previous'])}).",
                f"- Weeks reported: {s['weeks_reported']} of {p['weeks']}; coverage tier "
                f"{s['tier'] or 'not profiled'}.",
            ]
    lines.append("")

    lines += ["## Weekly values", "", "This period and the comparison period.", ""]
    if inc and not any(w["cases"] is not None for w in c["weekly"]) and c.get("monthly"):
        lines[-2] = ("Reported monthly: the calendar months overlapping this period and the "
                     "comparison period (incidence per 100,000 per week of the month).")
        lines += _table(
            ["Month", "Reported cases", "Incidence per 100,000"],
            [[_month(m["month_start"]) + (" (provisional)" if m["provisional"] else ""),
              _int(m["cases"]), _inc(m["incidence"])] for m in c["monthly"]], "lrr")
    elif inc:
        lines += _table(
            ["Week", "Reported cases", "Incidence per 100,000"],
            [[_d(w["week_start"]) + (" (provisional)" if w["provisional"] else ""),
              _int(w["cases"]), _inc(w["incidence"])] for w in c["weekly"]], "lrr")
    else:
        lines += _table(
            ["Week", "Positivity", "Detections", "Specimens"],
            [[_d(w["week_start"]) + (" (provisional)" if w["provisional"] else ""),
              _pct(w["positivity"]), _int(w["positives"]), _int(w["specimens_tested"])]
             for w in c["weekly"]], "lrrr")
    lines.append("")

    if inc and c["scope"] == "global" and c["top_movers"]:
        lines += ["## Largest changes in incidence", "",
                  f"Countries with ≥ {c['movers_min_cases']} reported cases in both periods; "
                  "weekly incidence per 100,000.", ""]
        lines += _table(
            ["Country", "Incidence", "Previous", "Change"],
            [[m["name"], _inc(m["incidence"]), _inc(m["previous_incidence"]),
              "—" if m["change_pct"] is None else f"{m['change_pct']:+.0f}%"]
             for m in c["top_movers"]], "lrrr")
        lines.append("")
    elif c["scope"] == "global" and c["top_movers"]:
        lines += ["## Largest changes in positivity", "",
                  f"Countries with ≥ {c['movers_min_specimens']} specimens in both periods.",
                  ""]
        lines += _table(
            ["Country", "Positivity", "Previous", "Change"],
            [[m["name"], _pct(m["positivity"]), _pct(m["previous_positivity"]),
              f"{m['change_pp']:+.1f} pp"] for m in c["top_movers"]], "lrrr")
        lines.append("")

    if c["scope"] == "country":
        lines += ["## Outlook", ""]
        if c["forecasts"]:
            lines += _table(
                ["Week", "Horizon", "Model", f"Forecast{unit}", "80% interval"],
                [[_d(f["target_week"]), f"+{f['horizon_weeks']} wk", f["model"],
                  v(f["point"]), f"{_interval(f['lo80'], f['hi80'], inc)}"]
                 for f in c["forecasts"]], "lllrr")
        else:
            lines.append("No forecast for this country in the current run.")
        lines.append("")
        t = c["thresholds"]
        if t and not t["quality_note"]:
            lines.append(f"Moving Epidemic Method levels for {t['season']}{unit}: epidemic "
                         f"threshold {v(t['epidemic_threshold'])}, medium "
                         f"{v(t['medium'])}, high {v(t['high'])}, very high "
                         f"{v(t['very_high'])} (from {t['n_seasons_used']} past seasons).")
        elif t:
            lines.append(f"MEM thresholds for {t['season']} are not usable: "
                         f"{t['quality_note']}.")
        else:
            lines.append("No MEM thresholds for this country.")
        lines.append("")

    lines += ["## Risk", ""]
    if c["risk"]:
        rows = [r for r in c["risk"] if c["scope"] == "country" or r["risk_level"] != "low"]
        if rows:
            lines += _table(
                ["Country", "Risk", "Week", f"Forecast (80%){unit}", "Epidemic threshold",
                 "High"],
                [[r["name"], r["risk_level"], _d(r["target_week"]),
                  f"{v(r['forecast_point'])} "
                  f"({_interval(r['forecast_lo80'], r['forecast_hi80'], inc)})",
                  v(r["epidemic_threshold"]), v(r["high_threshold"])] for r in rows],
                "lllrrr")
        low = sum(r["risk_level"] == "low" for r in c["risk"])
        if c["scope"] == "global":
            lines += ["", f"{low} further assessed countries are at low risk."]
    else:
        lines.append("Not assessed (no usable MEM thresholds or no 2-week forecast).")
    lines.append("")

    a = c["anomalies"]
    lines += ["## Anomalies", ""]
    if c["scope"] == "global":
        if a["countries"]:
            names = {w["iso3"]: w["name"] for w in a["weeks"]}
            lines += _table(
                ["Country", "Weeks flagged", "Highest severity", "Latest"],
                [[names[x["iso3"]], str(x["weeks_flagged"]), x["max_severity"],
                  _d(x["latest_week"])] for x in a["countries"]], "lrll")
        else:
            lines.append("No anomalous weeks in this period.")
    elif a["weeks"]:
        lines += _table(
            ["Week", f"Observed{unit}", "Expected", "Upper band", "Severity"],
            [[_d(w["week_start"]), v(w["observed"]), v(w["expected"]),
              v(w["upper_band"]), w["severity"]] for w in a["weeks"]], "lrrrl")
    else:
        lines.append("No anomalous weeks in this period.")
    lines.append("")

    h = c["hotspots"]
    lines += ["## Spatial clusters", ""]
    if not h["participants"]:
        lines.append("Not part of the hotspot analysis for this period." if c["iso3"]
                     else "No hotspot results for this period.")
    elif h["significant"]:
        lines += _table(
            ["Country", "4-week incidence per 100,000" if inc else "4-week positivity",
             "Gi*", "z", "p (FDR)", "Local Moran"],
            [[x["name"], v(x["value"]), GI[x["gi_star"]], f"{x['z']:+.2f}",
              f"{x['p_fdr']:.3f}", MORAN[x["local_moran"]]] for x in h["significant"]],
            "lrlrrl")
    else:
        lines.append(f"No significant clusters among {h['participants']} countries "
                     "(FDR < 0.05).")
    lines.append("")

    lines += ["## Alerts", ""]
    if c["alerts"]:
        for x in c["alerts"]:
            lines.append(f"- {_d(x['week_start'])} · {ALERT_LABELS[x['alert_type']]} "
                         f"({x['severity']}): {x['title']}")
    else:
        lines.append("No alerts in this period.")
    lines.append("")

    lines += ["## Limitations", ""] + [f"- {t}" for t in c["limitations"]] + [""]
    lines += ["## Sources", ""]
    lines += [f"- {src['attribution'] or src['name']}" for src in c["data"]["sources"]]
    runs = c["runs"]
    lines += ["", f"Reference week {_d(c['data']['reference_week'])}; forecast run "
              f"{runs['forecast'] or '—'}; detection run {runs['detection'] or '—'}. "
              f"Template v{c['template_version']}. Analytical tool only; not medical or "
              "public-health guidance.", ""]
    return "\n".join(lines)


def _interval(lo: float | None, hi: float | None, inc: bool) -> str:
    if inc:
        return f"{_inc(lo)}–{_inc(hi)}"
    return f"{_pct(lo, 0)}–{_pct(hi, 0)}"


def _dengue_summary(c: dict, s: dict, p: dict) -> list[str]:
    if c["scope"] == "global":
        out = [
            f"- Reported dengue cases (weekly reporters): **{_int(s['cases'])}** "
            f"({_rel(s['cases'], s['cases_previous'])}).",
            f"- Weekly incidence: **{_inc(s['incidence'])} per 100,000** "
            f"({_rel_inc(s['incidence'], s['incidence_previous'])}), pooled over "
            f"{_int(s['weekly_countries'])} weekly-reporting countries.",
            f"- Countries reporting: **{_int(s['countries_reporting'])}** "
            f"(previously {_int(s['countries_reporting_previous'])}), including monthly "
            "reporters.",
        ]
        if s["countries_with_anomaly"] is not None:
            out += [
                f"- Countries with an anomaly: **{_int(s['countries_with_anomaly'])}**.",
                f"- Countries in a Gi* hot spot (4 weeks to the period end): "
                f"**{_int(s['countries_in_hotspot'])}**.",
                f"- Latest 2-week forecast at or above the epidemic threshold: "
                f"**{_int(s['above_threshold'])}** of {_int(s['risk_assessed'])} countries "
                "with thresholds.",
            ]
        return out
    if not s["weeks_reported"] and not s["periods_reported"]:
        return ["- No dengue cases were reported in this period."]
    grain = ("weeks reported: "
             f"{s['weeks_reported']} of {p['weeks']}" if s["grain"] != "month" else
             "reported monthly (values from the overlapping calendar months)")
    return [
        f"- Reported cases: **{_int(s['cases'])}** "
        f"({_rel(s['cases'], s['cases_previous'])}).",
        f"- Weekly incidence: **{_inc(s['incidence'])} per 100,000** "
        f"({_rel_inc(s['incidence'], s['incidence_previous'])}).",
        f"- {grain[0].upper() + grain[1:]}; coverage tier {s['tier'] or 'not profiled'}.",
    ]
