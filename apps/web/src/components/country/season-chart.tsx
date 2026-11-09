"use client";

import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { formatInt, formatPct, formatWeek } from "@/lib/format";
import type { Season, ThresholdLevels } from "@/lib/types";

const PAST = "#64748b";

/**
 * Season-aligned positivity: the current season in the accent hue, earlier seasons as
 * recessive grey lines (COVID-disrupted seasons dashed). One y-axis.
 */
export function SeasonChart({
  seasons,
  minSpecimens,
  thresholds = null,
}: {
  seasons: Season[];
  minSpecimens: number;
  /** MEM levels of the current season, drawn as dashed reference lines. */
  thresholds?: ThresholdLevels | null;
}) {
  const option = useMemo<EChartsOption>(() => {
    const length = Math.max(...seasons.map((s) => s.points.length), 52);
    const byLabel = new Map(seasons.map((s) => [s.label, s]));
    // Draw past seasons first so the current season sits on top.
    const ordered = [...seasons].sort((a, b) => Number(a.is_current) - Number(b.is_current));
    return {
      animation: false,
      grid: { left: 44, right: 56, top: 16, bottom: 40 },
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        axisPointer: { type: "line", lineStyle: { color: CHART.muted, width: 1 } },
        formatter: (params: { seriesName: string; dataIndex: number }[]) => {
          const idx = params[0]?.dataIndex ?? 0;
          const rows = params
            .map((p) => byLabel.get(p.seriesName))
            .filter((s): s is Season => !!s)
            .sort((a, b) => (a.start < b.start ? 1 : -1))
            .map((s) => {
              const pt = s.points[idx];
              if (!pt) return "";
              const v = pt.reported && pt.positivity != null ? formatPct(pt.positivity) : "Not reported";
              const n = pt.reported ? ` <span style="color:${CHART.muted}">n=${formatInt(pt.specimens_tested)}</span>` : "";
              const color = s.is_current ? CHART.series : PAST;
              return `<div style="display:flex;justify-content:space-between;gap:14px"><span><span style="display:inline-block;width:8px;height:2px;background:${color};margin-right:6px;vertical-align:middle"></span>${s.label}${s.covid_disrupted ? " (COVID)" : ""}</span><span style="font-variant-numeric:tabular-nums">${v}${n}</span></div>`;
            });
          return `<div style="font-weight:600;margin-bottom:4px">Week ${idx + 1} of season</div>${rows.join("")}`;
        },
      },
      xAxis: {
        type: "category",
        data: Array.from({ length }, (_, i) => i + 1),
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10, interval: 3 },
        name: "Week of season",
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: CHART.muted, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        min: 0,
        // Keep the MEM levels in view (markLines do not extend the axis).
        max: thresholds
          ? (v: { max: number }) => Math.min(1, Math.ceil(Math.max(v.max, thresholds.very_high) * 20) / 20)
          : undefined,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: (v: number) => `${Math.round(v * 100)}%` },
      },
      series: ordered.map((s) => {
        const current = s.is_current;
        return {
          name: s.label,
          type: "line",
          // Only rate weeks with enough specimens; others are gaps.
          data: s.points.map((p) =>
            p.reported && p.positivity != null && (p.specimens_tested ?? 0) >= minSpecimens ? p.positivity : null,
          ),
          connectNulls: false,
          showSymbol: false,
          z: current ? 10 : 2,
          lineStyle: {
            width: current ? 2.5 : 1.25,
            color: current ? CHART.series : PAST,
            opacity: current ? 1 : 0.55,
            type: s.covid_disrupted ? [4, 3] : "solid",
          },
          emphasis: { focus: "series", lineStyle: { width: current ? 3 : 2, opacity: 1 } },
          // Only the current season is labelled; the table and tooltip name the rest.
          endLabel: { show: current, formatter: s.label, color: CHART.ink, fontSize: 10 },
          markLine:
            current && thresholds
              ? {
                  silent: true,
                  symbol: "none",
                  lineStyle: { color: CHART.muted, type: [5, 4], width: 1, opacity: 0.8 },
                  label: { position: "insideStartTop", color: CHART.muted, fontSize: 10 },
                  data: [
                    { yAxis: thresholds.epidemic_threshold, name: "Epidemic" },
                    { yAxis: thresholds.medium, name: "Medium" },
                    { yAxis: thresholds.high, name: "High" },
                    { yAxis: thresholds.very_high, name: "Very high" },
                  ].map((m) => ({ ...m, label: { formatter: `${m.name} ${formatPct(m.yAxis)}` } })),
                }
              : undefined,
        };
      }),
    };
  }, [seasons, minSpecimens, thresholds]);

  return <EChart option={option} ariaLabel="Weekly test positivity aligned by season" />;
}

export function SeasonTable({ seasons }: { seasons: Season[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="text-[11px] text-muted-foreground">
        <tr className="border-b border-border">
          <th className="py-1.5 text-left font-normal">Season</th>
          <th className="py-1.5 text-right font-normal">Peak</th>
          <th className="py-1.5 pl-3 text-right font-normal">Peak week</th>
          <th className="py-1.5 pl-3 text-right font-normal">Weeks</th>
          <th className="py-1.5 pl-3 text-right font-normal">Detections</th>
        </tr>
      </thead>
      <tbody className="metric">
        {[...seasons].reverse().map((s) => (
          <tr key={s.label} className="border-b border-border/60 last:border-0">
            <td className="py-1.5">
              {s.label}
              {s.is_current && <span className="ml-1.5 rounded bg-primary/15 px-1 text-[10px] text-primary">current</span>}
              {s.covid_disrupted && <span className="ml-1.5 rounded bg-muted px-1 text-[10px] text-muted-foreground">COVID</span>}
            </td>
            <td className="py-1.5 text-right">{formatPct(s.peak_positivity)}</td>
            <td className="py-1.5 text-right text-muted-foreground">{formatWeek(s.peak_week)}</td>
            <td className="py-1.5 text-right text-muted-foreground">
              {s.weeks_reported} / {s.points.length}
            </td>
            <td className="py-1.5 text-right">{formatInt(s.positives)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
