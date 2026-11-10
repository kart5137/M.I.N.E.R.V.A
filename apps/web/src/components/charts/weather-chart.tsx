"use client";

import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { formatWeek, isoWeekLabel } from "@/lib/format";

export interface WeatherPoint {
  week: string;
  value: number;
  /** Mean of the same ISO week over the baseline years; null without baseline. */
  normal: number | null;
}

/**
 * One weather measure per chart, one y-axis: the observed weekly value (teal line or bars)
 * against its normal (dashed neutral line), which is a reference, not a second series.
 */
export function WeatherChart({
  points,
  kind,
  name,
  unit,
  digits,
  ariaLabel,
  zeroBased = false,
  max,
}: {
  points: WeatherPoint[];
  kind: "line" | "bar";
  name: string;
  unit: string;
  digits: number;
  ariaLabel: string;
  zeroBased?: boolean;
  max?: number;
}) {
  const option = useMemo<EChartsOption>(() => {
    const fmt = (v: number) => `${v.toFixed(digits)} ${unit}`.trim();
    const byWeek = new Map(points.map((p) => [p.week, p]));
    const row = (k: string, v: string) =>
      `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:${CHART.muted}">${k}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`;
    return {
      animation: false,
      grid: { left: 40, right: 8, top: 8, bottom: 20 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: CHART.muted, width: 1 } },
        ...CHART.tooltip,
        formatter: (params: { axisValue: string }[]) => {
          const p = byWeek.get(params[0]?.axisValue);
          if (!p) return "";
          const diff = p.normal == null ? null : p.value - p.normal;
          return [
            `<div style="font-weight:600;margin-bottom:4px">${formatWeek(p.week)} <span style="color:${CHART.muted};font-weight:400">${isoWeekLabel(p.week)}</span></div>`,
            row(name, fmt(p.value)),
            row("Normal", p.normal == null ? "—" : fmt(p.normal)),
            diff == null ? "" : row("Difference", `${diff >= 0 ? "+" : "−"}${fmt(Math.abs(diff))}`),
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
        scale: !zeroBased,
        min: zeroBased ? 0 : undefined,
        max,
        splitNumber: 2,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: (v: number) => `${Math.round(v)}` },
      },
      series: [
        {
          name,
          type: kind,
          data: points.map((p) => p.value),
          showSymbol: false,
          symbolSize: 8,
          barCategoryGap: "20%",
          lineStyle: { width: 2, color: CHART.series },
          itemStyle: { color: CHART.series, borderRadius: [2, 2, 0, 0] },
          emphasis: { disabled: kind === "line" },
        },
        {
          name: "Normal",
          type: "line",
          data: points.map((p) => p.normal),
          showSymbol: false,
          connectNulls: false,
          lineStyle: { width: 1.5, color: CHART.muted, type: [4, 3] },
          itemStyle: { color: CHART.muted },
          emphasis: { disabled: true },
          z: 3,
        },
      ],
    };
  }, [points, kind, name, unit, digits, zeroBased, max]);

  return <EChart option={option} ariaLabel={ariaLabel} />;
}
