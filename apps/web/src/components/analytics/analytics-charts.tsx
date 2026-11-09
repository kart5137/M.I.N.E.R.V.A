"use client";

import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { formatInt, formatPct } from "@/lib/format";
import { POSITIVITY_BINS } from "@/lib/positivity-scale";
import type { Heatmap, TrendBucket, TrendSeries } from "@/lib/types";

export interface Metric {
  label: string;
  get: (b: TrendBucket) => number | null;
  value: (v: number) => string;
  axis: (v: number) => string;
}

const tooltipRow = (color: string, name: string, value: string, note = "") =>
  `<div style="display:flex;justify-content:space-between;gap:16px"><span><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-right:6px"></span>${name}</span><span style="font-variant-numeric:tabular-nums">${value}${note}</span></div>`;

/**
 * One line per series on a shared period axis. Partial buckets (extending past the
 * reference week) are drawn dashed. Each series is direct-labelled at its end.
 */
export function ComparisonChart({
  series,
  colors,
  metric,
}: {
  series: TrendSeries[];
  colors: Map<string, string>;
  metric: Metric;
}) {
  const option = useMemo<EChartsOption>(() => {
    const periods = [...new Set(series.flatMap((s) => s.buckets.map((b) => b.period_start)))].sort();
    const labels = new Map(series.flatMap((s) => s.buckets.map((b) => [b.period_start, b.label])));
    const lookup = new Map(series.map((s) => [s.key, new Map(s.buckets.map((b) => [b.period_start, b]))]));

    const lines = series.flatMap((s) => {
      const color = colors.get(s.key) ?? CHART.muted;
      const m = lookup.get(s.key)!;
      const firstPartial = periods.findIndex((p) => m.get(p)?.partial);
      const val = (p: string) => {
        const b = m.get(p);
        return b ? metric.get(b) : null;
      };
      const settled = periods.map((p, i) => (firstPartial >= 0 && i >= firstPartial ? null : val(p)));
      const partial = periods.map((p, i) =>
        firstPartial >= 0 && i >= firstPartial - 1 ? val(p) : null,
      );
      return [
        {
          name: s.label,
          id: `${s.key}:settled`,
          type: "line",
          data: settled,
          showSymbol: periods.length <= 40,
          symbolSize: 6,
          connectNulls: false,
          lineStyle: { width: 2, color },
          itemStyle: { color },
          labelLayout: { moveOverlap: "shiftY" },
          endLabel: firstPartial >= 0 ? undefined : { show: true, formatter: s.label, color: CHART.ink, fontSize: 10 },
        },
        {
          name: s.label,
          id: `${s.key}:partial`,
          type: "line",
          data: partial,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { width: 2, color, type: [4, 3], opacity: 0.8 },
          itemStyle: { color },
          labelLayout: { moveOverlap: "shiftY" },
          endLabel: firstPartial >= 0 ? { show: true, formatter: s.label, color: CHART.ink, fontSize: 10 } : undefined,
        },
      ];
    });

    return {
      animation: false,
      grid: { left: 52, right: 96, top: 36, bottom: 28 },
      legend: {
        top: 0,
        left: 0,
        textStyle: { color: CHART.muted, fontSize: 11 },
        itemWidth: 14,
        itemHeight: 3,
        data: series.map((s) => s.label),
      },
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        axisPointer: { type: "line", lineStyle: { color: CHART.muted, width: 1 } },
        formatter: (params: { dataIndex: number }[]) => {
          const p = periods[params[0]?.dataIndex ?? 0];
          const rows = series.map((s) => {
            const b = lookup.get(s.key)!.get(p);
            const v = b ? metric.get(b) : null;
            const note = b?.partial ? ` <span style="color:#f59e0b">partial</span>` : "";
            return tooltipRow(colors.get(s.key) ?? CHART.muted, s.label, v == null ? "—" : metric.value(v), note);
          });
          return `<div style="font-weight:600;margin-bottom:4px">${labels.get(p)}</div>${rows.join("")}`;
        },
      },
      xAxis: {
        type: "category",
        data: periods.map((p) => labels.get(p)),
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        min: 0,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: metric.axis },
      },
      series: lines,
    };
  }, [series, colors, metric]);

  return <EChart option={option} ariaLabel={`${metric.label} by period for ${series.map((s) => s.label).join(", ")}`} />;
}

const TYPE_A = "#9085e9";
const TYPE_B = "#199e70";

/** Influenza A vs B detections per period (stacked; typed detections only). */
export function SubtypeChart({ series }: { series: TrendSeries }) {
  const option = useMemo<EChartsOption>(() => {
    const b = series.buckets;
    return {
      animation: false,
      grid: { left: 52, right: 16, top: 32, bottom: 28 },
      legend: {
        top: 0,
        left: 0,
        textStyle: { color: CHART.muted, fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
        data: ["Influenza A", "Influenza B"],
      },
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(131,145,167,0.08)" } },
        formatter: (params: { dataIndex: number }[]) => {
          const x = b[params[0]?.dataIndex ?? 0];
          return [
            `<div style="font-weight:600;margin-bottom:4px">${x.label}${x.partial ? ` <span style="color:#f59e0b;font-weight:400">partial</span>` : ""}</div>`,
            tooltipRow(TYPE_A, "Influenza A", formatInt(x.inf_a)),
            tooltipRow(TYPE_B, "Influenza B", formatInt(x.inf_b)),
            `<div style="margin-top:4px;color:${CHART.muted}">A share: ${formatPct(x.share_a, 0)}</div>`,
          ].join("");
        },
      },
      xAxis: {
        type: "category",
        data: b.map((x) => x.label),
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: {
          color: CHART.muted,
          fontSize: 10,
          formatter: (v: number) => new Intl.NumberFormat("en-US", { notation: "compact" }).format(v),
        },
      },
      series: [
        { name: "Influenza A", type: "bar", stack: "t", data: b.map((x) => x.inf_a), itemStyle: { color: TYPE_A }, barCategoryGap: "25%" },
        {
          name: "Influenza B",
          type: "bar",
          stack: "t",
          data: b.map((x) => x.inf_b),
          itemStyle: { color: TYPE_B, borderRadius: [2, 2, 0, 0] },
        },
      ],
    };
  }, [series]);
  return <EChart option={option} ariaLabel={`Influenza A and B detections for ${series.label}`} />;
}

/** ISO week × year positivity, binned with the same scale as the map. */
export function PositivityHeatmap({ data }: { data: Heatmap }) {
  const option = useMemo<EChartsOption>(() => {
    const weeks = Array.from({ length: 53 }, (_, i) => i + 1);
    const years = data.years.map(String);
    const yearIndex = new Map(data.years.map((y, i) => [y, i]));
    const cells = data.cells.map((c) => {
      const lowN = (c.specimens_tested ?? 0) < data.min_specimens;
      return {
        value: [c.iso_week - 1, yearIndex.get(c.iso_year), lowN || c.positivity == null ? -1 : c.positivity],
        cell: c,
        itemStyle: c.is_provisional ? { opacity: 0.45 } : undefined,
      };
    });
    const pieces = [
      { value: -1, color: "#5b6475", label: `< ${data.min_specimens} specimens` },
      ...POSITIVITY_BINS.map((b, i) => ({
        gte: i === 0 ? 0 : POSITIVITY_BINS[i - 1].max,
        lt: b.max === Infinity ? 1.0001 : b.max,
        color: b.color,
        label: `${b.label}%`,
      })),
    ];
    return {
      animation: false,
      grid: { left: 44, right: 12, top: 8, bottom: 64 },
      tooltip: {
        ...CHART.tooltip,
        formatter: (p: { data: { cell: Heatmap["cells"][number] } }) => {
          const c = p.data.cell;
          return [
            `<div style="font-weight:600;margin-bottom:4px">${c.iso_year}-W${String(c.iso_week).padStart(2, "0")}${c.is_provisional ? ` <span style="color:#f59e0b;font-weight:400">provisional</span>` : ""}</div>`,
            `<div>Positivity: ${formatPct(c.positivity)}</div>`,
            `<div style="color:${CHART.muted}">Specimens: ${formatInt(c.specimens_tested)}</div>`,
          ].join("");
        },
      },
      xAxis: {
        type: "category",
        data: weeks,
        name: "ISO week",
        nameLocation: "middle",
        nameGap: 22,
        nameTextStyle: { color: CHART.muted, fontSize: 10 },
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10, interval: 3 },
        splitArea: { show: false },
      },
      yAxis: {
        type: "category",
        data: years,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10 },
      },
      visualMap: {
        type: "piecewise",
        dimension: 2,
        pieces,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        itemWidth: 12,
        itemHeight: 10,
        itemGap: 10,
        textStyle: { color: CHART.muted, fontSize: 10 },
      },
      series: [
        {
          type: "heatmap",
          data: cells,
          itemStyle: { borderColor: "#0d1322", borderWidth: 1, borderRadius: 2 },
          emphasis: { itemStyle: { borderColor: CHART.ink, borderWidth: 1 } },
        },
      ],
    };
  }, [data]);
  return <EChart option={option} ariaLabel={`Weekly test positivity by ISO week and year for ${data.label}`} />;
}
