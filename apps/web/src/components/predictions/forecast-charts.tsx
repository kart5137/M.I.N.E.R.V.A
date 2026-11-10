"use client";

import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { COLD, HOT } from "@/lib/detection-scale";
import { addWeeks, formatInt, formatPct, formatRate, formatSigned, formatWeek, weeksBetween } from "@/lib/format";
import type { Metric } from "@/lib/metric";
import type { CountryBacktest, Explanation, ForecastOut, SeriesPoint } from "@/lib/types";

const OBS = CHART.categorical[0];
const FC = CHART.categorical[1];
/** Interval bands: the forecast hue (amber, #bf8418) at two opacities. */
const BAND80 = "rgba(191,132,24,0.32)";
const BAND95 = "rgba(191,132,24,0.14)";
const INCREASE = HOT;
const DECREASE = COLD;

const row = (k: string, v: string, color?: string) =>
  `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:${CHART.muted}">${color ? `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-right:6px"></span>` : ""}${k}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`;

function bandSeries(name: string, lo: (number | null)[], hi: (number | null)[], color: string) {
  // Stacked areas: an invisible lower edge plus the (hi − lo) width.
  return [
    { name: `${name}-lo`, type: "line", data: lo, stack: name, lineStyle: { opacity: 0 }, symbol: "none", silent: true, connectNulls: true },
    {
      name: `${name}-band`,
      type: "line",
      data: hi.map((h, i) => (h == null || lo[i] == null ? null : h - (lo[i] as number))),
      stack: name,
      lineStyle: { opacity: 0 },
      areaStyle: { color },
      symbol: "none",
      silent: true,
      connectNulls: true,
    },
  ];
}

/** Observed weekly values (positivity, or dengue incidence), then the selected model's 1/2/4-week forecasts with
 * 80% and 95% intervals. */
export function ForecastChart({
  history,
  forecasts,
  minSpecimens,
  m,
}: {
  history: SeriesPoint[];
  forecasts: ForecastOut[];
  minSpecimens: number;
  m: Metric;
}) {
  const option = useMemo<EChartsOption>(() => {
    const origin = forecasts[0]?.origin_week ?? history.at(-1)?.week_start ?? "";
    const lastTarget = forecasts.reduce((m, f) => (f.target_week > m ? f.target_week : m), origin);
    const start = history[0]?.week_start ?? origin;
    const end = history.at(-1)?.week_start && history.at(-1)!.week_start > lastTarget ? history.at(-1)!.week_start : lastTarget;
    const weeks = Array.from({ length: weeksBetween(start, end) + 1 }, (_, i) => addWeeks(start, i));
    const obs = new Map(history.map((p) => [p.week_start, p]));
    const fc = new Map(forecasts.map((f) => [f.target_week, f]));
    const val = (p: SeriesPoint | undefined) => {
      if (!p || !p.reported) return null;
      if (m.key === "incidence") return p.incidence ?? null;
      return p.positivity != null && (p.specimens_tested ?? 0) >= minSpecimens ? p.positivity : null;
    };

    const settled = weeks.map((w) => (w <= origin ? val(obs.get(w)) : null));
    const provisional = weeks.map((w) => (w >= origin ? val(obs.get(w)) : null));
    const originValue = val(obs.get(origin));
    const point = weeks.map((w) => (w === origin ? originValue : fc.get(w)?.point ?? null));
    const lo80 = weeks.map((w) => (w === origin ? originValue : fc.get(w)?.lo80 ?? null));
    const hi80 = weeks.map((w) => (w === origin ? originValue : fc.get(w)?.hi80 ?? null));
    const lo95 = weeks.map((w) => (w === origin ? originValue : fc.get(w)?.lo95 ?? null));
    const hi95 = weeks.map((w) => (w === origin ? originValue : fc.get(w)?.hi95 ?? null));

    return {
      animation: false,
      grid: { left: 44, right: 16, top: 16, bottom: 28 },
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        axisPointer: { type: "line", lineStyle: { color: CHART.muted, width: 1 } },
        formatter: (params: { dataIndex: number }[]) => {
          const w = weeks[params[0]?.dataIndex ?? 0];
          const o = obs.get(w);
          const f = fc.get(w);
          const lines = [`<div style="font-weight:600;margin-bottom:4px">${formatWeek(w)}</div>`];
          if (o?.reported) {
            if (m.key === "incidence") {
              lines.push(row(w > origin ? "Observed (provisional)" : "Observed", `${m.format(o.incidence)} per 100k`, OBS));
              lines.push(row("Reported cases", formatInt(o.cases)));
            } else {
              lines.push(row(w > origin ? "Observed (provisional)" : "Observed", formatPct(o.positivity), OBS));
              lines.push(row("Specimens", formatInt(o.specimens_tested)));
            }
          } else if (w <= (history.at(-1)?.week_start ?? "")) lines.push(row("Observed", "Not reported"));
          if (f) {
            lines.push(row(`Forecast (+${f.horizon_weeks} wk)`, m.format(f.point), FC));
            lines.push(row("80% interval", `${m.format(f.lo80)} – ${m.format(f.hi80)}`));
            lines.push(row("95% interval", `${m.format(f.lo95)} – ${m.format(f.hi95)}`));
          }
          return lines.join("");
        },
      },
      xAxis: {
        type: "category",
        data: weeks,
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: {
          color: CHART.muted,
          fontSize: 10,
          hideOverlap: true,
          formatter: (v: string) => new Date(`${v}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }),
        },
      },
      // Fit the axis to observations and the 80% interval; a wide 95% band is clipped
      // (its full range is listed in the forecasts table).
      yAxis: {
        type: "value",
        min: 0,
        max: axisMax(Math.max(...settled.map((v) => v ?? 0), ...provisional.map((v) => v ?? 0), ...hi80.map((v) => v ?? 0)), m),
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: m.axis },
      },
      series: [
        ...bandSeries("95", lo95, hi95, BAND95),
        ...bandSeries("80", lo80, hi80, BAND80),
        {
          name: "Observed",
          type: "line",
          data: settled,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { width: 2, color: OBS },
          itemStyle: { color: OBS },
          markLine: {
            silent: true,
            symbol: "none",
            label: { formatter: "Forecast origin", color: CHART.muted, fontSize: 10, position: "insideEndTop" },
            lineStyle: { color: CHART.muted, type: [3, 3], width: 1 },
            data: [{ xAxis: origin }],
          },
        },
        {
          name: "Observed (provisional)",
          type: "line",
          data: provisional,
          showSymbol: true,
          symbol: "emptyCircle",
          symbolSize: 6,
          connectNulls: false,
          lineStyle: { width: 1.5, color: OBS, type: [4, 3], opacity: 0.8 },
          itemStyle: { color: OBS },
        },
        {
          name: "Forecast",
          type: "line",
          data: point,
          connectNulls: true,
          symbol: "circle",
          symbolSize: (v: number | null, p: { dataIndex: number }) => (weeks[p.dataIndex] === origin ? 0 : 8),
          lineStyle: { width: 2, color: FC },
          itemStyle: { color: FC, borderColor: "#0b2023", borderWidth: 2 },
        },
      ],
    };
  }, [history, forecasts, minSpecimens, m]);
  return <EChart option={option} ariaLabel={`Observed ${m.noun} with forecasts and prediction intervals`} />;
}

/** Upper axis bound: positivity capped at 100% in 5% steps; incidence to a round number. */
function axisMax(top: number, m: Metric): number {
  if (m.key === "positivity") return Math.min(1, Math.ceil(Math.max(0.05, top) * 1.2 * 20) / 20);
  const v = Math.max(top * 1.2, 0.1);
  const step = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / step) * step;
}

/** Past out-of-sample forecasts vs. what was later observed (one horizon). */
export function BacktestChart({ data, m }: { data: CountryBacktest; m: Metric }) {
  const option = useMemo<EChartsOption>(() => {
    const pts = data.points;
    const weeks = pts.map((p) => p.target_week);
    return {
      animation: false,
      grid: { left: 44, right: 16, top: 28, bottom: 28 },
      legend: {
        top: 0,
        left: 0,
        textStyle: { color: CHART.muted, fontSize: 11 },
        itemWidth: 14,
        itemHeight: 3,
        data: ["Observed", "Forecast"],
      },
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        formatter: (params: { dataIndex: number }[]) => {
          const p = pts[params[0]?.dataIndex ?? 0];
          return [
            `<div style="font-weight:600;margin-bottom:4px">${formatWeek(p.target_week)}</div>`,
            row("Observed", m.format(p.actual), OBS),
            row(`Forecast made ${formatWeek(p.origin_week)}`, m.format(p.point), FC),
            p.lo80 != null ? row("80% interval", `${m.format(p.lo80)} – ${m.format(p.hi80)}`) : row("80% interval", "not yet calibrated"),
          ].join("");
        },
      },
      xAxis: {
        type: "category",
        data: weeks,
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: {
          color: CHART.muted,
          fontSize: 10,
          hideOverlap: true,
          formatter: (v: string) => new Date(`${v}T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" }),
        },
      },
      yAxis: { type: "value", min: 0, splitLine: { lineStyle: { color: CHART.grid } }, axisLabel: { color: CHART.muted, fontSize: 10, formatter: m.axis } },
      series: [
        ...bandSeries("80", pts.map((p) => p.lo80), pts.map((p) => p.hi80), BAND80),
        { name: "Observed", type: "line", data: pts.map((p) => p.actual), showSymbol: false, lineStyle: { width: 2, color: OBS }, itemStyle: { color: OBS } },
        { name: "Forecast", type: "line", data: pts.map((p) => p.point), showSymbol: false, lineStyle: { width: 2, color: FC }, itemStyle: { color: FC } },
      ],
    };
  }, [data, m]);
  return <EChart option={option} ariaLabel={`Backtest forecasts compared with observed ${m.noun}`} />;
}

/** Display a feature value in readable units (influenza logit features as positivity; dengue level features as
 * incidence, changes as %, weather in its units). */
export function featureValue(feature: string, v: number | null, natural?: number | null, target = "positivity"): string {
  if (v == null) return "missing";
  if (target === "incidence") return dengueFeatureValue(feature, v, natural);
  const expit = (x: number) => 1 / (1 + Math.exp(-x));
  if (/^y_(lag\d|mean\d|last_year|peak52)$/.test(feature) || feature === "zone_mean_lag0") return formatPct(expit(v));
  if (feature === "log_tests_lag0") return `${formatInt(Math.expm1(v))} specimens`;
  if (feature === "tests_trend") return `${v >= 0 ? "+" : ""}${Math.round((Math.exp(v) - 1) * 100)}%`;
  if (feature === "weeks_into_season") return `week ${Math.round(v) + 1}`;
  if (feature.startsWith("season_")) return v ? "yes" : "no";
  if (feature === "lat" || feature === "abs_lat") return `${v.toFixed(1)}°`;
  return v.toFixed(2);
}

function dengueFeatureValue(feature: string, v: number, natural?: number | null): string {
  if (natural != null) return `${formatRate(natural)} per 100k`;
  const pctChange = (x: number) => formatSigned((Math.exp(x) - 1) * 100, 0, "%");
  if (/^y_diff\d$/.test(feature) || feature === "nbr_diff2") return pctChange(v);
  if (feature === "log_cases_mean4") return `${formatInt(Math.expm1(v))} cases/week`;
  if (feature === "lat" || feature === "abs_lat") return `${v.toFixed(1)}°`;
  if (feature.startsWith("temperature_anom")) return formatSigned(v, 1, " °C");
  if (feature.startsWith("temperature_")) return `${v.toFixed(1)} °C`;
  if (feature.startsWith("precipitation_anom")) return formatSigned(v, 0, " mm");
  if (feature.startsWith("precipitation_")) return `${Math.round(v)} mm`;
  if (feature.startsWith("humidity_anom")) return formatSigned(v, 1, " pts");
  if (feature.startsWith("humidity_")) return `${v.toFixed(0)}%`;
  return `${v.toFixed(2)} (log)`;
}

/** SHAP contributions (log-odds of positivity, or change in log incidence for dengue), largest first, plus the
 * remainder. */
export function ShapWaterfall({ data }: { data: Explanation }) {
  const option = useMemo<EChartsOption>(() => {
    const scale = data.target === "incidence" ? "log scale" : "log-odds";
    const items = [
      ...data.contributions.map((c) => ({
        name: c.label,
        value: c.shap_value,
        sub: featureValue(c.feature, c.feature_value, c.natural_value, data.target),
      })),
      { name: "All other features", value: data.other_features, sub: "" },
    ].reverse();
    return {
      animation: false,
      grid: { left: 180, right: 56, top: 8, bottom: 32 },
      tooltip: {
        ...CHART.tooltip,
        formatter: (p: { dataIndex: number }) => {
          const it = items[p.dataIndex];
          return `<div style="font-weight:600">${it.name}</div>${it.sub ? row("Value", it.sub) : ""}${row(`Effect (${scale})`, `${it.value >= 0 ? "+" : ""}${it.value.toFixed(3)}`)}`;
        },
      },
      xAxis: {
        type: "value",
        name: "← lowers forecast · raises forecast →",
        nameLocation: "middle",
        nameGap: 22,
        nameTextStyle: { color: CHART.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10 },
      },
      yAxis: {
        type: "category",
        data: items.map((i) => i.name),
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: {
          color: CHART.ink,
          fontSize: 11,
          formatter: (name: string) => {
            const it = items.find((i) => i.name === name);
            return it?.sub ? `${name}  {sub|${it.sub}}` : name;
          },
          rich: { sub: { color: CHART.muted, fontSize: 10 } },
        },
      },
      series: [
        {
          type: "bar",
          data: items.map((i) => ({ value: i.value, itemStyle: { color: i.value >= 0 ? INCREASE : DECREASE, borderRadius: 2 } })),
          barWidth: 12,
          label: {
            show: true,
            position: "right",
            color: CHART.muted,
            fontSize: 10,
            formatter: (p: { value: number }) => `${p.value >= 0 ? "+" : ""}${p.value.toFixed(2)}`,
          },
        },
      ],
    };
  }, [data]);
  return <EChart option={option} ariaLabel="Feature contributions to the forecast" />;
}
