"use client";

import { Plus, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { CHART } from "@/components/charts/echart";
import { Provenance } from "@/components/common/provenance";
import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { usePlatformStatus } from "@/hooks/use-platform-status";
import { useCountries, useHeatmap, useTrends } from "@/hooks/use-surveillance";
import { REGIONS, updateSearchParams } from "@/lib/filters";
import { addWeeks, formatCompact, formatInt, formatPct, formatSigned } from "@/lib/format";
import type { Granularity, TrendBucket, TrendSeries } from "@/lib/types";
import { cn } from "@/lib/utils";

import { ComparisonChart, type Metric, PositivityHeatmap, SubtypeChart } from "./analytics-charts";

const MAX_SERIES = CHART.categorical.length;
const DEFAULT_SERIES = "world,USA,AUS";

const GRANULARITIES: { key: Granularity; label: string; spans: Span[] }[] = [
  { key: "week", label: "Weekly", spans: ["1y", "2y", "5y"] },
  { key: "month", label: "Monthly", spans: ["2y", "5y", "10y"] },
  { key: "year", label: "Yearly", spans: ["10y", "all"] },
];
type Span = "1y" | "2y" | "5y" | "10y" | "all";
const SPAN_WEEKS: Record<Span, number | null> = { "1y": 52, "2y": 104, "5y": 260, "10y": 520, all: null };
const SPAN_LABEL: Record<Span, string> = { "1y": "1 year", "2y": "2 years", "5y": "5 years", "10y": "10 years", all: "All" };

const METRICS = {
  positivity: {
    label: "Test positivity",
    get: (b: TrendBucket) => b.positivity,
    value: (v: number) => formatPct(v),
    axis: (v: number) => `${Math.round(v * 100)}%`,
  },
  positives: {
    label: "Detections",
    get: (b: TrendBucket) => b.positives,
    value: (v: number) => formatInt(v),
    axis: (v: number) => formatCompact(v),
  },
  specimens: {
    label: "Specimens tested",
    get: (b: TrendBucket) => b.specimens_tested,
    value: (v: number) => formatInt(v),
    axis: (v: number) => formatCompact(v),
  },
  share_a: {
    label: "Influenza A share",
    get: (b: TrendBucket) => b.share_a,
    value: (v: number) => formatPct(v, 0),
    axis: (v: number) => `${Math.round(v * 100)}%`,
  },
} satisfies Record<string, Metric>;
type MetricKey = keyof typeof METRICS;

function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { key: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="flex gap-1 rounded-full border border-border bg-muted p-1 text-xs" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="radio"
          aria-checked={value === o.key}
          onClick={() => onChange(o.key)}
          className={cn(
            "rounded-full px-3 py-1 transition-colors",
            value === o.key ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Card({ title, subtitle, actions, children }: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>}
        </div>
        {actions}
      </header>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function AnalyticsView() {
  const params = useSearchParams();
  // One URL slot per colour: removing a series leaves an empty slot, so the others keep
  // their colours ("colour follows the entity").
  const slots = useMemo(
    () => (params.get("series") ?? DEFAULT_SERIES).split(",").slice(0, MAX_SERIES),
    [params],
  );
  const series = useMemo(() => slots.filter(Boolean), [slots]);
  const colors = useMemo(
    () => new Map(slots.flatMap((k, i) => (k ? [[k, CHART.categorical[i]] as [string, string]] : []))),
    [slots],
  );

  const g = (params.get("g") as Granularity) ?? "month";
  const gran = GRANULARITIES.find((x) => x.key === g) ?? GRANULARITIES[1];
  const spanParam = params.get("span") as Span | null;
  const span: Span = spanParam && gran.spans.includes(spanParam) ? spanParam : gran.spans[1] ?? gran.spans[0];
  const metricKey = (params.get("metric") as MetricKey) in METRICS ? (params.get("metric") as MetricKey) : "positivity";
  const metric = METRICS[metricKey];
  const focus = series.includes(params.get("focus") ?? "") ? params.get("focus")! : series[0] ?? null;

  const writeSlots = (next: string[]) => {
    while (next.length && !next[next.length - 1]) next.pop();
    updateSearchParams({ series: next.join(",") || null });
  };
  const add = (key: string) => {
    if (!key || series.includes(key) || series.length >= MAX_SERIES) return;
    const next = [...slots];
    const free = next.indexOf("");
    if (free >= 0) next[free] = key;
    else next.push(key);
    writeSlots(next);
  };
  const remove = (key: string) => writeSlots(slots.map((k) => (k === key ? "" : k)));

  // Span → from date, anchored on the latest week in the database.
  const platform = usePlatformStatus();
  const flu = "status" in platform ? platform.status.diseases.find((d) => d.key === "influenza") : undefined;
  const spanWeeks = SPAN_WEEKS[span];
  const from =
    flu?.latest_week && spanWeeks ? addWeeks(flu.latest_week, -(spanWeeks - 1)) : null; // null = API default / all
  const trends = useTrends(flu ? series : [], gran.key, spanWeeks ? from : "1995-01-01");
  const heat = useHeatmap(focus, 12);
  const countries = useCountries({ region: null, q: "", sort: "name", order: "asc", page: 1, pageSize: 300 });

  const data = trends.data;
  const focusSeries = data?.series.find((s) => s.key === focus);

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="Analytics"
        description="Compare countries, WHO regions and the world. Pooled positivity = positives ÷ specimens over reporting countries."
      />

      {/* Series picker */}
      <section className="flex flex-wrap items-center gap-2 panel p-3">
        <span className="text-xs text-muted-foreground">Series</span>
        {slots.map((key, i) =>
          key ? (
            <span key={key} className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-xs">
              <span className="size-2.5 rounded-[2px]" style={{ background: CHART.categorical[i] }} aria-hidden />
              {data?.series.find((s) => s.key === key)?.label ?? key}
              <button
                type="button"
                onClick={() => remove(key)}
                className="text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${key}`}
              >
                <X className="size-3.5" />
              </button>
            </span>
          ) : null,
        )}
        {series.length < MAX_SERIES ? (
          <label className="relative flex items-center">
            <Plus className="pointer-events-none absolute left-2 size-3.5 text-muted-foreground" aria-hidden />
            <select
              value=""
              onChange={(e) => add(e.target.value)}
              aria-label="Add a series"
              className="h-7 appearance-none rounded-md border border-dashed border-border bg-transparent pl-7 pr-2 text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
            >
              <option value="">Add series…</option>
              <optgroup label="Aggregates">
                {!series.includes("world") && <option value="world">World</option>}
                {REGIONS.filter((r) => !series.includes(`region:${r.code}`)).map((r) => (
                  <option key={r.code} value={`region:${r.code}`}>
                    {r.label} ({r.code})
                  </option>
                ))}
              </optgroup>
              <optgroup label="Countries with FluNet data">
                {countries.data?.items
                  .filter((c) => c.weeks_reported > 0 && !series.includes(c.iso3))
                  .map((c) => (
                    <option key={c.iso3} value={c.iso3}>
                      {c.name}
                    </option>
                  ))}
              </optgroup>
            </select>
          </label>
        ) : (
          <span className="text-[11px] text-muted-foreground">Maximum of {MAX_SERIES} series</span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Segmented
            label="Granularity"
            value={gran.key}
            options={GRANULARITIES.map((x) => ({ key: x.key, label: x.label }))}
            onChange={(v) => updateSearchParams({ g: v === "month" ? null : v, span: null })}
          />
          <Segmented
            label="Time span"
            value={span}
            options={gran.spans.map((s) => ({ key: s, label: SPAN_LABEL[s] }))}
            onChange={(v) => updateSearchParams({ span: v })}
          />
        </div>
      </section>

      {series.length === 0 && <p className="text-sm text-muted-foreground">Add at least one series to compare.</p>}
      {trends.error && <QueryError error={trends.error} />}

      {data && series.length > 0 && (
        <>
          <Card
            title={`${metric.label} by ${gran.key}`}
            subtitle="Dashed segments are partial periods that include provisional or not-yet-reported weeks."
            actions={
              <Segmented
                label="Metric"
                value={metricKey}
                options={(Object.keys(METRICS) as MetricKey[]).map((k) => ({ key: k, label: METRICS[k].label }))}
                onChange={(v) => updateSearchParams({ metric: v === "positivity" ? null : v })}
              />
            }
          >
            <div className={cn("h-80", trends.isPlaceholderData && "opacity-60")}>
              <ComparisonChart series={data.series} colors={colors} metric={metric} />
            </div>
          </Card>

          <GrowthTable series={data.series} colors={colors} granularity={gran.key} />

          <div className="grid gap-4 xl:grid-cols-2">
            <Card
              title={`Influenza A / B detections · ${focusSeries?.label ?? ""}`}
              subtitle="Typed detections only (weeks reporting both A and B)."
              actions={<FocusPicker series={data.series} focus={focus} />}
            >
              <div className="h-72">{focusSeries && <SubtypeChart series={focusSeries} />}</div>
            </Card>
            <Card
              title={`Seasonal heatmap · ${heat.data?.label ?? ""}`}
              subtitle="Pooled test positivity by ISO week and year (last 12 years). Faded cells are provisional."
              actions={<FocusPicker series={data.series} focus={focus} />}
            >
              {heat.error && <QueryError error={heat.error} />}
              <div className="h-72">{heat.data && <PositivityHeatmap data={heat.data} />}</div>
            </Card>
          </div>
          <Provenance meta={data.meta} />
        </>
      )}
    </div>
  );
}

function FocusPicker({ series, focus }: { series: TrendSeries[]; focus: string | null }) {
  return (
    <select
      value={focus ?? ""}
      onChange={(e) => updateSearchParams({ focus: e.target.value })}
      aria-label="Series shown in this chart"
      className="h-7 rounded-md border border-border bg-background px-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
    >
      {series.map((s) => (
        <option key={s.key} value={s.key}>
          {s.label}
        </option>
      ))}
    </select>
  );
}

/** Latest complete period vs. the one before, per series (growth rates). */
function GrowthTable({
  series,
  colors,
  granularity,
}: {
  series: TrendSeries[];
  colors: Map<string, string>;
  granularity: Granularity;
}) {
  return (
    <Card title="Growth" subtitle={`Latest complete ${granularity} vs. the previous ${granularity}. Partial periods are excluded.`}>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Growth table">
        <table className="w-full min-w-[640px] text-xs">
          <thead className="text-[11px] text-muted-foreground">
            <tr className="border-b border-border">
              <th className="py-1.5 text-left font-normal">Series</th>
              <th className="py-1.5 text-right font-normal">Period</th>
              <th className="py-1.5 text-right font-normal">Positivity</th>
              <th className="py-1.5 text-right font-normal">Change</th>
              <th className="py-1.5 text-right font-normal">Detections</th>
              <th className="py-1.5 text-right font-normal">Change</th>
              <th className="py-1.5 text-right font-normal">Countries reporting</th>
            </tr>
          </thead>
          <tbody className="metric">
            {series.map((s) => {
              const b = [...s.buckets].reverse().find((x) => !x.partial);
              return (
                <tr key={s.key} className="border-b border-border/60 last:border-0">
                  <td className="py-1.5">
                    <span className="mr-2 inline-block size-2.5 rounded-[2px] align-middle" style={{ background: colors.get(s.key) }} />
                    {s.label}
                  </td>
                  {b ? (
                    <>
                      <td className="py-1.5 text-right text-muted-foreground">{b.label}</td>
                      <td className="py-1.5 text-right">{formatPct(b.positivity)}</td>
                      <td className="py-1.5 text-right text-muted-foreground">
                        {b.positivity_change_pp == null ? "—" : formatSigned(b.positivity_change_pp, 1, " pp")}
                      </td>
                      <td className="py-1.5 text-right">{formatInt(b.positives)}</td>
                      <td className="py-1.5 text-right text-muted-foreground">
                        {b.positives_change_pct == null ? "—" : formatSigned(b.positives_change_pct, 0, "%")}
                      </td>
                      <td className="py-1.5 text-right text-muted-foreground">{formatInt(b.countries_reporting)}</td>
                    </>
                  ) : (
                    <td colSpan={6} className="py-1.5 text-right text-muted-foreground">
                      No complete period in range
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
