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
    lines += ["## Summary", ""]
    if c["scope"] == "global":
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
    lines += _table(
        ["Week", "Positivity", "Detections", "Specimens"],
        [[_d(w["week_start"]) + (" (provisional)" if w["provisional"] else ""),
          _pct(w["positivity"]), _int(w["positives"]), _int(w["specimens_tested"])]
         for w in c["weekly"]], "lrrr")
    lines.append("")

    if c["scope"] == "global" and c["top_movers"]:
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
                ["Week", "Horizon", "Model", "Forecast", "80% interval"],
                [[_d(f["target_week"]), f"+{f['horizon_weeks']} wk", f["model"],
                  _pct(f["point"]), f"{_pct(f['lo80'], 0)}–{_pct(f['hi80'], 0)}"]
                 for f in c["forecasts"]], "lllrr")
        else:
            lines.append("No forecast for this country in the current run.")
        lines.append("")
        t = c["thresholds"]
        if t and not t["quality_note"]:
            lines.append(f"Moving Epidemic Method levels for {t['season']}: epidemic "
                         f"threshold {_pct(t['epidemic_threshold'])}, medium "
                         f"{_pct(t['medium'])}, high {_pct(t['high'])}, very high "
                         f"{_pct(t['very_high'])} (from {t['n_seasons_used']} past seasons).")
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
                ["Country", "Risk", "Week", "Forecast (80%)", "Epidemic threshold", "High"],
                [[r["name"], r["risk_level"], _d(r["target_week"]),
                  f"{_pct(r['forecast_point'])} ({_pct(r['forecast_lo80'], 0)}–"
                  f"{_pct(r['forecast_hi80'], 0)})", _pct(r["epidemic_threshold"]),
                  _pct(r["high_threshold"])] for r in rows], "lllrrr")
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
            ["Week", "Observed", "Expected", "Upper band", "Severity"],
            [[_d(w["week_start"]), _pct(w["observed"]), _pct(w["expected"]),
              _pct(w["upper_band"]), w["severity"]] for w in a["weeks"]], "lrrrl")
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
            ["Country", "4-week positivity", "Gi*", "z", "p (FDR)", "Local Moran"],
            [[x["name"], _pct(x["value"]), GI[x["gi_star"]], f"{x['z']:+.2f}",
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
