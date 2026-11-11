"use client";

/**
 * Analytics for yearly diseases (malaria): compare the world, WHO regions and countries
 * on one World Malaria Report measure, year by year. Estimates carry WHO's uncertainty
 * range in the tooltip; reported cases are what national programmes reported.
 */

import { useQueries } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { useAnnualCountries } from "@/hooks/use-annual";
import { apiGet } from "@/lib/api";
import type { DiseaseKey } from "@/lib/diseases";
import { REGIONS, updateSearchParams, withParams } from "@/lib/filters";
import { formatCompact, formatInt } from "@/lib/format";
import type { AnnualSeries } from "@/lib/types";
import { cn } from "@/lib/utils";

import { type SeriesOption, SeriesPicker } from "./series-picker";

const MAX_SERIES = CHART.categorical.length;
const DEFAULT_SERIES = "GLOBAL,AFR,NGA";
/** Measures worth comparing across areas (counts and rates). */
const MEASURES = ["est_incidence", "est_cases", "est_deaths", "est_mortality", "reported_cases"] as const;
type Measure = (typeof MEASURES)[number];
const RATE: Record<Measure, boolean> = {
  est_incidence: true,
  est_cases: false,
  est_deaths: false,
  est_mortality: true,
  reported_cases: false,
};

function fmt(m: Measure, v: number): string {
  return RATE[m] ? v.toFixed(v < 10 ? 2 : 1) : formatInt(v);
}

export function AnnualAnalytics({ disease }: { disease: DiseaseKey }) {
  const params = useSearchParams();
  const slots = useMemo(() => (params.get("series") ?? DEFAULT_SERIES).split(",").slice(0, MAX_SERIES), [params]);
  const areas = slots.filter(Boolean);
  const measure: Measure = MEASURES.includes(params.get("metric") as Measure)
    ? (params.get("metric") as Measure)
    : "est_incidence";

  const results = useQueries({
    queries: areas.map((a) => ({
      queryKey: ["annual", disease, "series", a],
      queryFn: () => apiGet<AnnualSeries>(withParams("/annual/series", `disease=${disease}&area=${a}`)),
      staleTime: 30 * 60_000,
    })),
  });
  const countries = useAnnualCountries(disease, null, null);
  const loaded = results.flatMap((r) => (r.data ? [r.data] : []));
  const error = results.find((r) => r.error)?.error ?? null;
  // Region rows come back named by their code; show the region's name.
  const nameOf = (s: AnnualSeries) =>
    s.scope === "region" ? (REGIONS.find((r) => r.code === s.area)?.label ?? s.name) : s.name;
  const labels = useMemo(
    () => new Map(loaded.map((s) => [s.area, nameOf(s)])),
    [loaded],
  );
  const measureLabels = loaded[0]?.measures ?? {};
  const seriesOptions: SeriesOption[] = [
    ...(areas.includes("GLOBAL") ? [] : [{ value: "GLOBAL", label: "World", group: "aggregate" as const }]),
    ...REGIONS.filter((r) => !areas.includes(r.code)).map((r) => ({
      value: r.code,
      label: r.label,
      code: r.code,
      group: "aggregate" as const,
    })),
    ...(countries.data?.items ?? [])
      .filter((c) => !areas.includes(c.iso3))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((c) => ({
        value: c.iso3,
        label: c.name,
        code: c.iso3,
        hint: REGIONS.find((r) => r.code === c.who_region)?.label,
        group: "country" as const,
      })),
  ];

  const writeSlots = (next: string[]) => {
    while (next.length && !next[next.length - 1]) next.pop();
    updateSearchParams({ series: next.join(",") || null });
  };
  const add = (key: string) => {
    if (!key || areas.includes(key) || areas.length >= MAX_SERIES) return;
    const next = [...slots];
    const free = next.indexOf("");
    if (free >= 0) next[free] = key;
    else next.push(key);
    writeSlots(next);
  };
  const remove = (key: string) => writeSlots(slots.map((k) => (k === key ? "" : k)));

  const option = useMemo<EChartsOption>(() => {
    const years = [...new Set(loaded.flatMap((s) => s.points.map((p) => p.year)))].sort((a, b) => a - b);
    const lines = slots.flatMap((key, i) => {
      const s = loaded.find((x) => x.area === key);
      if (!key || !s) return [];
      const by = new Map(s.points.map((p) => [p.year, p.values[measure]]));
      const name = labels.get(s.area) ?? s.name;
      return [
        {
          name,
          type: "line" as const,
          data: years.map((y) => by.get(y)?.value ?? null),
          connectNulls: false,
          showSymbol: false,
          lineStyle: { width: 2, color: CHART.categorical[i] },
          itemStyle: { color: CHART.categorical[i] },
          labelLayout: { moveOverlap: "shiftY" as const },
          endLabel: { show: true, formatter: name, color: CHART.ink, fontSize: 10 },
          ranges: years.map((y) => by.get(y)),
        },
      ];
    });
    return {
      animation: false,
      grid: { left: 56, right: 96, top: 12, bottom: 28 },
      tooltip: {
        ...CHART.tooltip,
        trigger: "axis",
        formatter: (ps: { axisValue: string; seriesIndex: number; dataIndex: number; color: string }[]) => {
          const head = `<div style="font-weight:600;margin-bottom:4px">${ps[0]?.axisValue ?? ""}</div>`;
          return (
            head +
            ps
              .map((p) => {
                const v = lines[p.seriesIndex].ranges[p.dataIndex];
                if (!v) return "";
                const range = v.low != null && v.high != null ? ` (${fmt(measure, v.low)}–${fmt(measure, v.high)})` : "";
                return `<div style="display:flex;justify-content:space-between;gap:16px"><span><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${p.color};margin-right:6px"></span>${lines[p.seriesIndex].name}</span><span style="font-variant-numeric:tabular-nums">${fmt(measure, v.value)}${range}</span></div>`;
              })
              .join("")
          );
        },
      },
      xAxis: {
        type: "category",
        data: years.map(String),
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        min: 0,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: (v: number) => (RATE[measure] ? String(v) : formatCompact(v)) },
      },
      series: lines.map((l) => ({ ...l, ranges: undefined })),
    };
  }, [loaded, slots, measure, labels]);

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="Analytics"
        eyebrow="Malaria · yearly estimates"
        description="Compare the world, WHO regions and countries year by year. Estimates come with WHO's uncertainty range (in the tooltip)."
      />
      <section className="flex flex-wrap items-center gap-2 panel p-3">
        <span className="text-xs text-muted-foreground">Series</span>
        {slots.map((key, i) =>
          key ? (
            <span key={key} className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-xs">
              <span className="size-2.5 rounded-[2px]" style={{ background: CHART.categorical[i] }} aria-hidden />
              {labels.get(key) ?? key}
              <button type="button" onClick={() => remove(key)} className="text-muted-foreground hover:text-foreground" aria-label={`Remove ${labels.get(key) ?? key}`}>
                <X className="size-3.5" />
              </button>
            </span>
          ) : null,
        )}
        {areas.length < MAX_SERIES ? (
          <SeriesPicker
            options={seriesOptions}
            onAdd={add}
            nextColor={CHART.categorical[slots.includes("") ? slots.indexOf("") : slots.length]}
            countriesLabel="Countries with malaria data"
            remaining={MAX_SERIES - areas.length}
          />
        ) : (
          <span className="text-[11px] text-muted-foreground">Maximum of {MAX_SERIES} series</span>
        )}
      </section>

      {error && <QueryError error={error} />}
      <section className="panel p-4">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-sm font-medium">{measureLabels[measure] ?? "Estimated cases per 1,000 population at risk"} by year</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Gaps are years without a value, never zero. WHO revises the whole estimate series each year.
            </p>
          </div>
          <div className="flex flex-wrap gap-1 rounded-full border border-border bg-muted p-1 text-xs" role="radiogroup" aria-label="Measure">
            {MEASURES.map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={measure === m}
                onClick={() => updateSearchParams({ metric: m === "est_incidence" ? null : m })}
                className={cn(
                  "rounded-full px-3 py-1 transition-colors",
                  measure === m ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {SHORT[m]}
              </button>
            ))}
          </div>
        </header>
        <div className="mt-3 h-96">
          {areas.length === 0 ? (
            <p className="text-sm text-muted-foreground">Add at least one series to compare.</p>
          ) : (
            <EChart option={option} ariaLabel={`${measureLabels[measure] ?? measure} by year`} />
          )}
        </div>
      </section>
    </div>
  );
}

const SHORT: Record<Measure, string> = {
  est_incidence: "Incidence",
  est_cases: "Est. cases",
  est_deaths: "Est. deaths",
  est_mortality: "Mortality",
  reported_cases: "Reported cases",
};
