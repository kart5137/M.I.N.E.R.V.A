"use client";

import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { QueryError } from "@/components/common/query-state";
import { useCountryDetection } from "@/hooks/use-detection";
import { useCountryTimeseries } from "@/hooks/use-surveillance";
import { RISK_SCALE } from "@/lib/detection-scale";
import { formatRate, formatWeek } from "@/lib/format";
import type { EndemicChannel } from "@/lib/types";

/** Zone fills: a neutral usual range, and the risk scale's amber above the channel. */
const ZONE_LOW = `${CHART.muted2}73`;
const ZONE_MODERATE = `${RISK_SCALE.colors[1]}80`;

/** "2019–2021, 2023" from [2019, 2020, 2021, 2023]. */
export function yearRanges(years: number[]): string {
  const out: string[] = [];
  let start: number | null = null;
  years.forEach((y, i) => {
    start = start ?? y;
    if (i + 1 === years.length || years[i + 1] !== y + 1) {
      out.push(start === y ? String(y) : `${start}–${y}`);
      start = null;
    }
  });
  return out.join(", ");
}

function Swatch({ color, line, dashed }: { color: string; line?: boolean; dashed?: boolean }) {
  return line ? (
    <span
      className="inline-block w-4 align-middle"
      style={{ borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}` }}
      aria-hidden
    />
  ) : (
    <span className="inline-block size-2.5 rounded-[2px] align-middle" style={{ background: color }} aria-hidden />
  );
}

/**
 * Endemic channel (dengue): this year's reported weekly incidence over the country's usual
 * range for each week (from earlier years), with the 2-week forecast behind the risk level.
 */
export function ChannelCard({ iso3 }: { iso3: string }) {
  const det = useCountryDetection(iso3);
  const ch = det.data?.channel ?? null;
  const latest = det.data?.meta.latest_week;
  const from = ch?.weeks[0]?.week_start ?? latest ?? "";
  const series = useCountryTimeseries(ch ? iso3 : null, from, latest ?? from, "dengue");
  const risk = det.data?.risk ?? null;

  return (
    <section className="panel p-4">
      <h2 className="text-sm font-medium">Endemic channel{ch ? ` ${ch.year}` : ""}</h2>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        {ch
          ? `Reported weekly incidence per 100,000 against this country's usual range for each week: the same week ±1 in ${yearRanges(ch.years_used)} (highest year ${yearRanges(ch.excluded_years)} left out). Risk compares the 2-week forecast with the top of the channel and the 90th percentile.`
          : "The usual weekly range from earlier years."}
      </p>
      {(det.error || series.error) && <QueryError error={(det.error ?? series.error) as Error} />}
      {det.data && !ch && (
        <p className="mt-2 text-xs text-muted-foreground">
          No endemic channel: {det.data.thresholds_reason ?? "it needs 5 complete weekly reporting years among the last 7"}.
        </p>
      )}
      {ch && (
        <ChannelChart
          channel={ch}
          observed={(series.data?.points ?? []).map((p) => ({
            week: p.week_start,
            value: p.reported ? (p.incidence ?? null) : null,
            provisional: p.is_provisional,
          }))}
          forecast={risk && risk.method === "endemic_channel" ? { week: risk.target_week, value: risk.forecast_point } : null}
        />
      )}
      {ch && (
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <li className="flex items-center gap-1.5"><Swatch color={ZONE_LOW} /> Usual range (up to the 75th percentile)</li>
          <li className="flex items-center gap-1.5"><Swatch color={ZONE_MODERATE} /> Above the channel (75th–90th percentile)</li>
          <li className="flex items-center gap-1.5"><Swatch color={CHART.muted} line dashed /> Median</li>
          <li className="flex items-center gap-1.5"><Swatch color={CHART.series} line /> Reported (dashed: provisional)</li>
          {risk?.method === "endemic_channel" && (
            <li className="flex items-center gap-1.5"><Swatch color={CHART.ink} /> 2-week forecast</li>
          )}
        </ul>
      )}
    </section>
  );
}

function ChannelChart({
  channel,
  observed,
  forecast,
}: {
  channel: EndemicChannel;
  observed: { week: string; value: number | null; provisional: boolean }[];
  forecast: { week: string; value: number } | null;
}) {
  const option = useMemo<EChartsOption>(() => {
    const weeks = channel.weeks.map((w) => w.week_start);
    const obs = new Map(observed.map((o) => [o.week, o]));
    const settled = weeks.map((w) => {
      const o = obs.get(w);
      return o && !o.provisional ? o.value : null;
    });
    // Provisional weeks continue from the last settled week so the line stays joined.
    const firstProv = weeks.findIndex((w) => obs.get(w)?.provisional);
    const provisional = weeks.map((w, i) => {
      const o = obs.get(w);
      if (o?.provisional) return o.value;
      return firstProv > 0 && i === firstProv - 1 ? settled[i] : null;
    });
    const fcIndex = forecast ? weeks.indexOf(forecast.week) : -1;
    return {
      animation: false,
      grid: { left: 48, right: 16, top: 12, bottom: 28 },
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        axisPointer: { type: "line", lineStyle: { color: CHART.muted, width: 1 } },
        formatter: (params: { dataIndex: number }[]) => {
          const i = params[0]?.dataIndex ?? 0;
          const c = channel.weeks[i];
          const o = obs.get(c.week_start);
          const row = (k: string, v: string) =>
            `<div style="display:flex;justify-content:space-between;gap:14px"><span style="color:${CHART.muted}">${k}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`;
          const reported = o?.value != null ? `${formatRate(o.value)}${o.provisional ? " (provisional)" : ""}` : "Not reported";
          return [
            `<div style="font-weight:600;margin-bottom:4px">Week ${c.iso_week} · ${formatWeek(c.week_start)}</div>`,
            row("Reported", reported),
            i === fcIndex && forecast ? row("2-week forecast", formatRate(forecast.value)) : "",
            row("Median", formatRate(c.median)),
            row("Top of channel (75th)", formatRate(c.q75)),
            row("90th percentile", formatRate(c.p90)),
          ].join("");
        },
      },
      xAxis: {
        type: "category",
        data: weeks,
        boundaryGap: false,
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10, interval: 7, formatter: (v: string) => formatWeek(v).replace(/ \d{4}$/, "") },
      },
      yAxis: {
        type: "value",
        min: 0,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: (v: number) => formatRate(v) },
      },
      series: [
        {
          name: "Usual range",
          type: "line",
          stack: "zones",
          data: channel.weeks.map((w) => w.q75),
          showSymbol: false,
          lineStyle: { width: 0 },
          areaStyle: { color: ZONE_LOW },
          silent: true,
        },
        {
          name: "Above the channel",
          type: "line",
          stack: "zones",
          data: channel.weeks.map((w) => Math.max(w.p90 - w.q75, 0)),
          showSymbol: false,
          lineStyle: { width: 0 },
          areaStyle: { color: ZONE_MODERATE },
          silent: true,
        },
        {
          name: "Median",
          type: "line",
          data: channel.weeks.map((w) => w.median),
          showSymbol: false,
          lineStyle: { width: 1, type: [4, 3], color: CHART.muted },
          silent: true,
        },
        {
          name: "Reported",
          type: "line",
          data: settled,
          showSymbol: false,
          connectNulls: false,
          z: 10,
          lineStyle: { width: 2, color: CHART.series },
        },
        {
          name: "Reported (provisional)",
          type: "line",
          data: provisional,
          showSymbol: false,
          connectNulls: false,
          z: 10,
          lineStyle: { width: 2, color: CHART.series, type: [4, 3] },
        },
        {
          name: "2-week forecast",
          type: "scatter",
          data: weeks.map((_, i) => (i === fcIndex && forecast ? forecast.value : null)),
          symbol: "diamond",
          symbolSize: 10,
          z: 12,
          itemStyle: { color: CHART.ink, borderColor: "#0b2023", borderWidth: 2 },
        },
      ],
    };
  }, [channel, observed, forecast]);

  return (
    <div className="mt-2 h-64">
      <EChart option={option} ariaLabel={`Endemic channel ${channel.year}: reported weekly incidence against the usual range`} />
    </div>
  );
}
