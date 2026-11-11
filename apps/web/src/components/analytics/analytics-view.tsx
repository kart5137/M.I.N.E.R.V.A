"use client";

import { X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { CHART } from "@/components/charts/echart";
import { Provenance } from "@/components/common/provenance";
import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { usePlatformStatus } from "@/hooks/use-platform-status";
import { useCountries, useHeatmap, useTrends } from "@/hooks/use-surveillance";
import { rampFor } from "@/lib/disease-palette";
import { DISEASES, type DiseaseInfo, type DiseaseKey } from "@/lib/diseases";
import { REGIONS, updateSearchParams, useFilters } from "@/lib/filters";
import { addWeeks, formatCompact, formatInt, formatPct, formatRate, formatSigned } from "@/lib/format";
import type { Granularity, TrendBucket, TrendSeries } from "@/lib/types";
import { cn } from "@/lib/utils";

import { AnnualAnalytics } from "./annual-analytics";
import { ComparisonChart, IncidenceHeatmap, type Metric, PositivityHeatmap, SubtypeChart } from "./analytics-charts";
import { type SeriesOption, SeriesPicker } from "./series-picker";
import { WeatherContext } from "./weather-context";

const MAX_SERIES = CHART.categorical.length;
/** Default comparison per disease: the world and steady recent reporters. */
const DEFAULT_SERIES: Record<DiseaseKey, string> = {
  influenza: "world,USA,AUS",
  dengue: "world,BRA,COL",
  malaria: "",
  cholera: "world,YEM,NGA",
  covid19: "world,GBR,POL",
};

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

/** Case-based diseases (weekly reports only). Deaths only where the source has them. */
const CASE_METRICS = {
  incidence: {
    label: "Cases per 100k / week",
    get: (b: TrendBucket) => b.incidence ?? null,
    value: (v: number) => formatRate(v),
    axis: (v: number) => formatRate(v),
  },
  cases: {
    label: "Reported cases",
    get: (b: TrendBucket) => b.cases ?? null,
    value: (v: number) => formatInt(v),
    axis: (v: number) => formatCompact(v),
  },
  deaths: {
    label: "Reported deaths",
    get: (b: TrendBucket) => b.deaths ?? null,
    value: (v: number) => formatInt(v),
    axis: (v: number) => formatCompact(v),
  },
} satisfies Record<string, Metric>;
type MetricKey = string;

function metricsFor(info: DiseaseInfo): Record<string, Metric> {
  if (!info.caseBased) return METRICS;
  // Dengue reports carry no deaths.
  return info.key === "dengue" ? { incidence: CASE_METRICS.incidence, cases: CASE_METRICS.cases } : CASE_METRICS;
}

const DESCRIPTION = {
  lab: "Compare countries, WHO regions and the world. Pooled positivity = positives ÷ specimens over reporting countries.",
  cases:
    "Compare countries, WHO regions and the world. Weekly reports only; cases per 100,000 per week are pooled over the countries that reported (gaps are not zeros).",
};

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
  const [filters] = useFilters();
  const info = DISEASES[filters.disease];
  // Yearly diseases (malaria) compare yearly measures; weekly ones compare weekly reports.
  return info.grain === "year" ? <AnnualAnalytics disease={info.key} /> : <WeeklyAnalytics info={info} />;
}

function WeeklyAnalytics({ info }: { info: DiseaseInfo }) {
  const params = useSearchParams();
  const METRIC_SET = metricsFor(info);
  const defaultMetric = info.caseBased ? "incidence" : "positivity";
  // One URL slot per colour: removing a series leaves an empty slot, so the others keep
  // their colours ("colour follows the entity").
  const slots = useMemo(
    () => (params.get("series") ?? DEFAULT_SERIES[info.key]).split(",").slice(0, MAX_SERIES),
    [params, info.key],
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
  const metricKey: MetricKey = (params.get("metric") ?? "") in METRIC_SET ? params.get("metric")! : defaultMetric;
  const metric = METRIC_SET[metricKey];
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
  const status = "status" in platform ? platform.status.diseases.find((d) => d.key === info.key) : undefined;
  const spanWeeks = SPAN_WEEKS[span];
  const from =
    status?.latest_week && spanWeeks ? addWeeks(status.latest_week, -(spanWeeks - 1)) : null; // null = API default / all
  const trends = useTrends(status ? series : [], gran.key, spanWeeks ? from : "1995-01-01", info.key);
  const heat = useHeatmap(focus, 12, info.key);
  const countries = useCountries({
    disease: info.key,
    region: null,
    q: "",
    sort: "name",
    order: "asc",
    page: 1,
    pageSize: 300,
  });

  const seriesOptions = useMemo<SeriesOption[]>(
    () => [
      ...(series.includes("world") ? [] : [{ value: "world", label: "World", group: "aggregate" as const }]),
      ...REGIONS.filter((r) => !series.includes(`region:${r.code}`)).map((r) => ({
        value: `region:${r.code}`,
        label: r.label,
        code: r.code,
        group: "aggregate" as const,
      })),
      ...(countries.data?.items ?? [])
        .filter((c) => (info.caseBased ? c.last_reported_week != null : c.weeks_reported > 0) && !series.includes(c.iso3))
        .map((c) => ({
          value: c.iso3,
          label: c.name,
          code: c.iso3,
          hint: REGIONS.find((r) => r.code === c.who_region)?.label,
          group: "country" as const,
        })),
    ],
    [series, countries.data, info.caseBased],
  );

  const data = trends.data;
  const focusSeries = data?.series.find((s) => s.key === focus);
  // Weather is per country: the focused series if it is one, else the first country.
  const weatherSeries =
    focusSeries?.kind === "country" ? focusSeries : data?.series.find((s) => s.kind === "country");

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="Analytics"
        eyebrow={`${info.label} surveillance`}
        description={info.caseBased ? DESCRIPTION.cases : DESCRIPTION.lab}
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
          <SeriesPicker
            options={seriesOptions}
            onAdd={add}
            nextColor={CHART.categorical[slots.includes("") ? slots.indexOf("") : slots.length]}
            countriesLabel={info.caseBased ? "Countries with weekly reports" : "Countries with FluNet data"}
            remaining={MAX_SERIES - series.length}
          />
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
                options={Object.keys(METRIC_SET).map((k) => ({ key: k, label: METRIC_SET[k].label }))}
                onChange={(v) => updateSearchParams({ metric: v === defaultMetric ? null : v })}
              />
            }
          >
            <div className={cn("h-80", trends.isPlaceholderData && "opacity-60")}>
              <ComparisonChart series={data.series} colors={colors} metric={metric} />
            </div>
          </Card>

          <GrowthTable series={data.series} colors={colors} granularity={gran.key} caseBased={info.caseBased} />

          {info.caseBased ? (
            <div className={cn("grid gap-4", info.key === "dengue" && "xl:grid-cols-2")}>
              <Card
                title={`Seasonal heatmap · ${heat.data?.label ?? ""}`}
                subtitle="Cases per 100,000 per week by ISO week and year (weekly reports, last 12 years). Faded cells are provisional; empty cells are weeks without a report."
                actions={<FocusPicker series={data.series} focus={focus} />}
              >
                {heat.error && <QueryError error={heat.error} />}
                <div className="h-72">{heat.data && <IncidenceHeatmap data={heat.data} palette={rampFor(info.key)} />}</div>
              </Card>
              {info.key === "dengue" && (
                <Card
                  title={`Weather and dengue · ${weatherSeries?.label ?? ""}`}
                  subtitle="Last 3 years at the country's weather point. Context, not cause: in the backtest, weather did not clearly improve dengue forecasts."
                  actions={
                    weatherSeries && (
                      <FocusPicker
                        series={data.series.filter((s) => s.kind === "country")}
                        focus={weatherSeries.key}
                      />
                    )
                  }
                >
                  {weatherSeries && status?.latest_week ? (
                    <WeatherContext iso3={weatherSeries.key} name={weatherSeries.label} latestWeek={status.latest_week} />
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Weather is per country: add a country to the series to see its rainfall and temperature.
                    </p>
                  )}
                </Card>
              )}
            </div>
          ) : (
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
          )}
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
  caseBased,
}: {
  series: TrendSeries[];
  colors: Map<string, string>;
  granularity: Granularity;
  caseBased: boolean;
}) {
  return (
    <Card title="Growth" subtitle={`Latest complete ${granularity} vs. the previous ${granularity}. Partial periods are excluded.`}>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Growth table">
        <table className="w-full min-w-[640px] text-xs">
          <thead className="text-[11px] text-muted-foreground">
            <tr className="border-b border-border">
              <th className="py-1.5 text-left font-normal">Series</th>
              <th className="py-1.5 text-right font-normal">Period</th>
              <th className="py-1.5 text-right font-normal">{caseBased ? "Per 100k / week" : "Positivity"}</th>
              <th className="py-1.5 text-right font-normal">{caseBased ? "Reported cases" : "Change"}</th>
              <th className="py-1.5 text-right font-normal">{caseBased ? "Deaths" : "Detections"}</th>
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
                  {b && caseBased ? (
                    <>
                      <td className="py-1.5 text-right text-muted-foreground">{b.label}</td>
                      <td className="py-1.5 text-right">{formatRate(b.incidence)}</td>
                      <td className="py-1.5 text-right">{formatInt(b.cases)}</td>
                      <td className="py-1.5 text-right">{b.deaths == null ? "—" : formatInt(b.deaths)}</td>
                      <td className="py-1.5 text-right text-muted-foreground">
                        {b.cases_change_pct == null ? "—" : formatSigned(b.cases_change_pct, 0, "%")}
                      </td>
                      <td className="py-1.5 text-right text-muted-foreground">{formatInt(b.countries_reporting)}</td>
                    </>
                  ) : b ? (
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
