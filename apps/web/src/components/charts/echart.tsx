"use client";

import { BarChart, HeatmapChart, LineChart, ScatterChart } from "echarts/charts";
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
  ScatterChart,
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
  ink: "#efe8da",
  muted: "#9fb5af",
  grid: "#16312f",
  axis: "#2a5558",
  /** Single-series colour (categorical slot 1). */
  series: "#1f9e8f",
  provisional: "rgba(159,181,175,0.08)",
  /**
   * Categorical series slots, validated on the card surface #0b2023 (dark band, chroma,
   * adjacent CVD ≥ 12.8, normal-vision ≥ 19.4, contrast ≥ 3:1). Assign by entity, never
   * by rank.
   */
  categorical: ["#1f9e8f", "#bf8418", "#8f6fe0", "#d4584a", "#3f83d6", "#c4508a"],
  muted2: "#4d6662",
  selection: "rgba(242,169,59,0.07)",
  tooltip: {
    backgroundColor: "#0e2629",
    borderColor: "#1c3a3d",
    textStyle: { color: "#efe8da", fontSize: 12 },
    extraCssText: "border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,.5);",
  },
} as const;

export function EChart({
  option,
  className,
  ariaLabel,
  onAxisClick,
}: {
  option: EChartsOption;
  className?: string;
  ariaLabel: string;
  /** Click anywhere in the plot: index of the nearest x category (category x-axis). */
  onAxisClick?: (index: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onAxisClick);

  useEffect(() => {
    clickRef.current = onAxisClick;
  }, [onAxisClick]);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, null, { renderer: "canvas" });
    chartRef.current = chart;
    chart.getZr().on("click", (e: { offsetX: number; offsetY: number }) => {
      if (!clickRef.current) return;
      const pt = [e.offsetX, e.offsetY];
      if (!chart.containPixel({ gridIndex: 0 }, pt)) return;
      const x = chart.convertFromPixel({ xAxisIndex: 0 }, pt);
      const idx = Array.isArray(x) ? x[0] : x;
      if (typeof idx === "number" && Number.isFinite(idx)) clickRef.current(Math.round(idx));
    });
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

  return (
    <div
      ref={ref}
      role="img"
      aria-label={ariaLabel}
      className={cn("h-full w-full", onAxisClick && "cursor-pointer", className)}
    />
  );
}
