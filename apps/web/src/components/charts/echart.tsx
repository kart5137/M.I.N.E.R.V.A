"use client";

import { BarChart, HeatmapChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

echarts.use([
  LineChart,
  BarChart,
  HeatmapChart,
  GridComponent,
  LegendComponent,
  VisualMapComponent,
  TooltipComponent,
  MarkAreaComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export type EChartsOption = echarts.EChartsCoreOption;

/** Chart chrome shared by every chart: recessive axes and grid, text in ink tokens. */
export const CHART = {
  ink: "#dce3ee",
  muted: "#8391a7",
  grid: "#1c2740",
  axis: "#2b3a5a",
  series: "#3987e5",
  provisional: "rgba(131,145,167,0.10)",
  /** Categorical series slots (validated, dark surface). Assign by entity, never by rank. */
  categorical: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"],
  muted2: "#4a5568",
  selection: "rgba(34,211,238,0.08)",
  tooltip: {
    backgroundColor: "#0f1729",
    borderColor: "#1c2740",
    textStyle: { color: "#dce3ee", fontSize: 12 },
    extraCssText: "border-radius:6px;box-shadow:0 8px 24px rgba(0,0,0,.4);",
  },
} as const;

export function EChart({
  option,
  className,
  ariaLabel,
}: {
  option: EChartsOption;
  className?: string;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "canvas" });
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  return <div ref={ref} role="img" aria-label={ariaLabel} className={cn("h-full w-full", className)} />;
}
