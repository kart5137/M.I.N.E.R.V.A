"use client";

import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { formatWeek, isoWeekLabel } from "@/lib/format";

export interface WeeklyPoint {
  week: string;
  /** null = not reported (drawn as a gap, never as zero). */
  value: number | null;
  provisional: boolean;
  /** Extra tooltip lines, already formatted. */
  details?: [string, string][];
}

export interface WeeklyChartProps {
  points: WeeklyPoint[];
  kind: "line" | "bar";
  seriesName: string;
  formatValue: (v: number) => string;
  formatAxis: (v: number) => string;
  /** Shaded window, e.g. the selected period. */
  highlight?: { start: string; end: string } | null;
  ariaLabel: string;
  compact?: boolean;
  className?: string;
}

/** One measure per chart, one y-axis. Provisional weeks are shaded and drawn dashed (line) or faded (bars). */
export function WeeklyChart({
  points,
  kind,
  seriesName,
  formatValue,
  formatAxis,
  highlight,
  ariaLabel,
  compact = false,
  className,
}: WeeklyChartProps) {
  const option = useMemo<EChartsOption>(() => {
    const firstProv = points.find((p) => p.provisional)?.week;
    const last = points.at(-1)?.week;
    const areas: unknown[] = [];
    if (highlight) {
      areas.push([{ xAxis: highlight.start, itemStyle: { color: CHART.selection } }, { xAxis: highlight.end }]);
    }
    if (firstProv && last) {
      areas.push([{ xAxis: firstProv, itemStyle: { color: CHART.provisional } }, { xAxis: last }]);
    }
    // Provisional weeks are drawn as a separate, visibly tentative series: dashed line
    // (joined to the last settled week) or faded bars.
    const provIdx = points.findIndex((p) => p.provisional);
    const settled = points.map((p) => (p.provisional ? null : p.value));
    const tentative = points.map((p, i) =>
      provIdx >= 0 && (i >= provIdx || (kind === "line" && i === provIdx - 1)) ? p.value : null,
    );
    const byWeek = new Map(points.map((p) => [p.week, p]));

    return {
      animation: false,
      grid: compact
        ? { left: 36, right: 8, top: 8, bottom: 20 }
        : { left: 48, right: 16, top: 24, bottom: 28 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: CHART.muted, width: 1 } },
        ...CHART.tooltip,
        formatter: (params: { axisValue: string }[]) => {
          const p = byWeek.get(params[0]?.axisValue);
          if (!p) return "";
          const rows: [string, string][] = [
            [seriesName, p.value == null ? "Not reported" : formatValue(p.value)],
            ...(p.details ?? []),
          ];
          return [
            `<div style="font-weight:600;margin-bottom:4px">${formatWeek(p.week)} <span style="color:${CHART.muted};font-weight:400">${isoWeekLabel(p.week)}</span></div>`,
            ...rows.map(
              ([k, v]) =>
                `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:${CHART.muted}">${k}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`,
            ),
            p.provisional
              ? `<div style="margin-top:4px;color:#f59e0b;font-size:11px">Provisional: reporting still incomplete</div>`
              : "",
          ].join("");
        },
      },
      xAxis: {
        type: "category",
        data: points.map((p) => p.week),
        boundaryGap: kind === "bar",
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: {
          color: CHART.muted,
          fontSize: 10,
          hideOverlap: true,
          formatter: (v: string) =>
            new Date(`${v}T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" }),
        },
      },
      yAxis: {
        type: "value",
        min: 0,
        splitNumber: compact ? 2 : 4,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: formatAxis },
      },
      series: [
        {
          name: seriesName,
          type: kind,
          data: settled,
          connectNulls: false,
          showSymbol: false,
          symbolSize: 8,
          barCategoryGap: "20%",
          barGap: "-100%",
          lineStyle: { width: 2, color: CHART.series },
          itemStyle: { color: CHART.series, borderRadius: [2, 2, 0, 0] },
          emphasis: { disabled: kind === "line" },
          markArea: { silent: true, data: areas },
        },
        {
          name: `${seriesName} (provisional)`,
          type: kind,
          data: tentative,
          connectNulls: false,
          showSymbol: false,
          barCategoryGap: "20%",
          lineStyle: { width: 2, color: CHART.series, type: [4, 3], opacity: 0.8 },
          itemStyle: { color: CHART.series, opacity: 0.4, borderRadius: [2, 2, 0, 0] },
          emphasis: { disabled: kind === "line" },
        },
      ],
    };
  }, [points, kind, seriesName, formatValue, formatAxis, highlight, compact]);

  return <EChart option={option} ariaLabel={ariaLabel} className={className} />;
}
