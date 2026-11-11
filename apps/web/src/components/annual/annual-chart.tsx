"use client";

import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { formatAnnualRate, formatCount } from "@/lib/annual-scale";
import { formatCompact } from "@/lib/format";
import type { MeasureValue } from "@/lib/types";

type Point = { year: number; values: Partial<Record<string, MeasureValue>> };

const EST = CHART.categorical[0];
const REPORTED = CHART.categorical[1];
const CONFIRMED = CHART.categorical[2];

function row(name: string, value: string, color?: string) {
  const swatch = color
    ? `<span style="display:inline-block;width:8px;height:2px;background:${color};margin-right:6px;vertical-align:middle"></span>`
    : "";
  return `<div style="display:flex;justify-content:space-between;gap:14px"><span style="color:${CHART.muted}">${swatch}${name}</span><span style="font-variant-numeric:tabular-nums">${value}</span></div>`;
}

/**
 * One yearly measure with its uncertainty band (WHO estimates), optionally with reported
 * counts as separate lines. One y-axis: every series is the same unit.
 */
export function AnnualBandChart({
  points,
  measure,
  label,
  highlight = null,
  reported = false,
  rate = false,
}: {
  points: Point[];
  measure: string;
  label: string;
  highlight?: number | null;
  /** Also draw reported_cases and confirmed_cases (case counts only). */
  reported?: boolean;
  rate?: boolean;
}) {
  const option = useMemo<EChartsOption>(() => {
    const years = points.map((p) => String(p.year));
    const fmt = rate ? formatAnnualRate : formatCount;
    const get = (k: string) => points.map((p) => p.values[k]?.value ?? null);
    const lo = points.map((p) => p.values[measure]?.low ?? null);
    const hi = points.map((p) => p.values[measure]?.high ?? null);
    const hasBand = lo.some((v) => v != null);
    const legend = [label, ...(reported ? ["Reported (confirmed + presumed)", "Confirmed"] : [])];
    const hl = highlight == null ? -1 : years.indexOf(String(highlight));
    return {
      animation: false,
      grid: { left: 52, right: 12, top: reported ? 30 : 12, bottom: 24 },
      legend: reported
        ? { top: 0, left: 0, data: legend, textStyle: { color: CHART.muted, fontSize: 11 }, itemWidth: 14, itemHeight: 3 }
        : undefined,
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        formatter: (params: { dataIndex: number }[]) => {
          const p = points[params[0]?.dataIndex ?? 0];
          const m = p.values[measure];
          const lines = [
            `<div style="font-weight:600;margin-bottom:4px">${p.year}</div>`,
            row(label, m ? fmt(m.value) : "No estimate", EST),
            m?.low != null && m.high != null ? row("Uncertainty range", `${fmt(m.low)} – ${fmt(m.high)}`) : "",
          ];
          if (reported) {
            lines.push(row("Reported", p.values.reported_cases ? formatCount(p.values.reported_cases.value) : "Not reported", REPORTED));
            lines.push(row("Confirmed", p.values.confirmed_cases ? formatCount(p.values.confirmed_cases.value) : "Not reported", CONFIRMED));
          }
          return lines.join("");
        },
      },
      xAxis: {
        type: "category",
        data: years,
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        min: 0,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: (v: number) => (rate ? fmt(v) : formatCompact(v)) },
      },
      series: [
        ...(hasBand
          ? [
              { name: "band-low", type: "line" as const, data: lo, stack: "band", lineStyle: { opacity: 0 }, showSymbol: false, silent: true },
              {
                name: "band",
                type: "line" as const,
                data: hi.map((h, i) => (h == null || lo[i] == null ? null : h - (lo[i] as number))),
                stack: "band",
                lineStyle: { opacity: 0 },
                areaStyle: { color: EST, opacity: 0.18 },
                showSymbol: false,
                silent: true,
              },
            ]
          : []),
        {
          name: label,
          type: "line",
          data: get(measure),
          showSymbol: false,
          lineStyle: { width: 2, color: EST },
          itemStyle: { color: EST },
          markPoint:
            hl >= 0 && get(measure)[hl] != null
              ? { symbol: "circle", symbolSize: 8, data: [{ coord: [hl, get(measure)[hl] as number] }], itemStyle: { color: CHART.ink }, label: { show: false } }
              : undefined,
        },
        ...(reported
          ? [
              { name: "Reported (confirmed + presumed)", type: "line" as const, data: get("reported_cases"), showSymbol: true, symbolSize: 5, lineStyle: { width: 2, color: REPORTED }, itemStyle: { color: REPORTED } },
              { name: "Confirmed", type: "line" as const, data: get("confirmed_cases"), showSymbol: true, symbolSize: 5, lineStyle: { width: 1.5, color: CONFIRMED, type: [4, 3] }, itemStyle: { color: CONFIRMED } },
            ]
          : []),
      ],
    };
  }, [points, measure, label, highlight, reported, rate]);
  return <EChart option={option} ariaLabel={`${label} by year`} />;
}
