"use client";

import { rampFor } from "@/lib/disease-palette";
import { ArrowDownRight, ArrowRight, ArrowUpRight, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { QueryError } from "@/components/common/query-state";
import { AnnualOverview } from "@/components/annual/annual-overview";
import { Provenance } from "@/components/common/provenance";
import { WeeklyChart, type WeeklyPoint } from "@/components/charts/weekly-chart";
import { Globe } from "@/components/globe";
import { PageHeader } from "@/components/layout/page-header";
import { AlertListCard } from "@/components/intelligence/alert-list-card";
import { PlatformStatusPanel } from "@/components/overview/platform-status-panel";
import { IncidenceLegend } from "@/components/surveillance/incidence-legend";
import { PositivityLegend } from "@/components/surveillance/positivity-legend";
import { useMediaQuery } from "@/hooks/use-element-size";
import { usePlatformStatus } from "@/hooks/use-platform-status";
import { useGlobalSurveillance, useOverview } from "@/hooks/use-surveillance";
import { DISEASES } from "@/lib/diseases";
import { type Filters, REGIONS, diseaseParam, filterQuery, useFilters, withParams } from "@/lib/filters";
import {
  formatCompact,
  formatInt,
  formatPct,
  formatRate,
  formatSigned,
  formatWeek,
  windowLabel,
} from "@/lib/format";
import type { Kpi, Overview, TrendPoint } from "@/lib/types";
import { cn } from "@/lib/utils";

const INTRO = {
  influenza: "Global influenza surveillance from WHO FluNet laboratory data.",
  dengue: "Global dengue surveillance from cases reported to WHO.",
  malaria: "Yearly malaria estimates and reported cases from the WHO World Malaria Report.",
  cholera: "Weekly cholera cases and deaths reported to WHO by countries with outbreaks.",
} as const;

/** Yearly diseases (malaria) have their own overview; weekly ones use the dashboard below. */
export function OverviewDashboard() {
  const [filters] = useFilters();
  return DISEASES[filters.disease].grain === "year" ? <AnnualOverview /> : <WeeklyOverview />;
}

function WeeklyOverview() {
  const platform = usePlatformStatus();
  const [filters, setFilters] = useFilters();
  const overview = useOverview(filters);
  const caseBased = DISEASES[filters.disease].caseBased;
  const features = DISEASES[filters.disease].features;
  const intro = INTRO[filters.disease];

  if (platform.kind !== "ready") {
    return (
      <Page>
        <PageHeader title="Overview" eyebrow={`${DISEASES[filters.disease].label} surveillance`} description={intro} />
        <div className="max-w-md">
          <PlatformStatusPanel />
        </div>
      </Page>
    );
  }
  if (overview.error) {
    return (
      <Page>
        <PageHeader title="Overview" eyebrow={`${DISEASES[filters.disease].label} surveillance`} description={intro} />
        <QueryError error={overview.error} />
      </Page>
    );
  }
  const data = overview.data;
  const region = REGIONS.find((r) => r.code === filters.region)?.label ?? "All WHO regions";
  const description = data
    ? `${filters.weeks === 1 ? "1 week" : `${filters.weeks} weeks`} ending ${formatWeek(data.window.end)} · ${region}`
    : "Loading…";

  return (
    <div className="flex flex-1 flex-col">
      <Hero
        filters={filters}
        data={data}
        description={description}
        onLatest={filters.to ? () => setFilters({ to: null }) : undefined}
      />
      <Page>
        {data?.window.includes_provisional && <ProvisionalNotice />}
        <div className="grid gap-3 sm:grid-cols-2 lg:hidden">
          <KpiTiles data={data} weeks={filters.weeks} caseBased={caseBased} />
          {data && features.detection && <Signals kpis={data.kpis} weeks={filters.weeks} filters={filters} />}
        </div>
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
          <TrendCard key={filters.disease} data={data} caseBased={caseBased} />
          {caseBased ? <TopIncidenceMovers data={data} /> : <TopMovers data={data} />}
        </div>
        {features.reports && <AlertListCard region={filters.region} to={data?.window.end ?? null} limit={5} />}
        {data && <Provenance meta={data.meta} />}
      </Page>
    </div>
  );
}

function Page({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-1 flex-col gap-5 p-4 lg:p-6">{children}</div>;
}

function ProvisionalNotice() {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-status-warn/35 bg-status-warn/8 px-3.5 py-2.5 text-xs text-foreground">
      <TriangleAlert className="size-4 shrink-0 text-status-warn" aria-hidden />
      This period includes provisional weeks. Countries are still reporting, so totals will rise.
    </div>
  );
}

/* ---------- Hero: full-bleed globe with floating KPIs ---------- */

const CTA =
  "pointer-events-auto inline-flex shrink-0 items-center justify-center gap-1.5 rounded-full bg-primary font-semibold text-primary-foreground shadow-[0_8px_24px_-8px_rgb(242_169_59/0.6)] transition-transform hover:-translate-y-px";

function Hero({
  filters,
  data,
  description,
  onLatest,
}: {
  filters: Filters;
  data: Overview | undefined;
  description: string;
  onLatest?: () => void;
}) {
  const global = useGlobalSurveillance(filters);
  const router = useRouter();
  const lg = useMediaQuery("(min-width: 1024px)");
  const xl = useMediaQuery("(min-width: 1280px)");
  // Keep the globe centred in the space the floating panels leave free.
  const insets = { top: lg ? 0 : 96, left: lg ? 320 : 0, right: xl ? 344 : 0, bottom: lg ? 0 : 88 };
  const surveillanceHref = `/surveillance?${filterQuery(filters)}`;
  const info = DISEASES[filters.disease];

  return (
    <section
      aria-label="Global picture"
      className="relative h-[600px] overflow-hidden border-b border-border/70 lg:h-[clamp(640px,calc(100dvh-104px),880px)]"
    >
      <Globe
        className="absolute inset-0"
        insets={insets}
        values={global.data?.countries}
        windowWeeks={global.data?.window.weeks}
        measure={info.caseBased ? "incidence" : "positivity"}
        layers={{ positivity: true, detections: true }}
        palette={info.caseBased ? rampFor(info.key) : null}
        pitch={24}
        clouds
        onCountryClick={(c) => router.push(`${surveillanceHref}&country=${c.iso3}`)}
      />
      {/* Edge vignette so the floating panels read against the globe. */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "linear-gradient(90deg, rgb(3 11 13 / 0.7) 0%, transparent 30%, transparent 72%, rgb(3 11 13 / 0.55) 100%)",
        }}
        aria-hidden
      />

      <div className="pointer-events-none absolute inset-0 flex flex-col gap-4 p-4 lg:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="pointer-events-auto max-w-sm">
            <div className="eyebrow text-teal">{info.label} surveillance</div>
            <h1 className="mt-1.5 text-2xl font-semibold tracking-tight lg:text-[30px]">Global overview</h1>
            <p className="mt-1 text-[13px] text-muted-foreground">{description}</p>
            {onLatest && (
              <button
                type="button"
                onClick={onLatest}
                className="mt-2 rounded-full border border-input bg-card/80 px-3 py-1 text-xs text-muted-foreground hover:text-foreground"
              >
                Back to latest settled week
              </button>
            )}
          </div>
          <Link href={surveillanceHref} className={cn(CTA, "h-9 px-4 text-xs xl:hidden")}>
            Explore the globe <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </div>

        <div className="flex min-h-0 flex-1 gap-4">
          <div className="hidden w-[280px] flex-col gap-3 lg:flex">
            <KpiTiles data={data} weeks={filters.weeks} caseBased={info.caseBased} glass />
          </div>
          <div className="flex-1" />
          <div className="hidden w-[320px] flex-col gap-3 xl:flex">
            {data && info.features.detection && <Signals kpis={data.kpis} weeks={filters.weeks} filters={filters} glass />}
            <Link href={surveillanceHref} className={cn(CTA, "h-10 px-4 text-[13px]")}>
              Explore Global Surveillance <ArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
        </div>

        <div className="flex items-end justify-between gap-3">
          {/* lg+: sit beside the KPI column (280px + 16px gap), not under it. */}
          <div className="panel-glass pointer-events-auto w-64 rounded-xl p-3 lg:ml-[296px]">
            {info.caseBased ? <IncidenceLegend disease={info.label} palette={rampFor(info.key)} /> : <PositivityLegend />}
          </div>
          {global.error && <QueryError error={global.error} className="pointer-events-auto text-xs text-status-error" />}
        </div>
      </div>
    </section>
  );
}

/* ---------- KPIs ---------- */

function delta(k: Kpi, weeks: number): string | null {
  if (k.change == null) return null;
  const period = `vs previous ${weeks === 1 ? "week" : `${weeks} weeks`}`;
  if (k.change_unit === "percent") return `${formatSigned(k.change, 1, "%")} ${period}`;
  if (k.change_unit === "pp") return `${formatSigned(k.change, 1, " pp")} ${period}`;
  return `${formatSigned(k.change, 0)} ${period}`;
}

/** Tiny trend line for a stat tile. Decorative: the number and delta carry the content. */
function Sparkline({ values }: { values: (number | null)[] }) {
  const pts = values.flatMap((v, i) => (v == null ? [] : [[i, v] as const]));
  if (pts.length < 2) return null;
  const span = values.length - 1;
  const ys = pts.map((p) => p[1]);
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const W = 96;
  const H = 30;
  const x = (i: number) => (i / span) * (W - 6) + 3;
  const y = (v: number) => (hi === lo ? H / 2 : H - 3 - ((v - lo) / (hi - lo)) * (H - 6));
  const line = pts.map(([i, v], k) => `${k ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const [li, lv] = pts[pts.length - 1];
  const area = `${line}L${x(li).toFixed(1)},${H}L${x(pts[0][0]).toFixed(1)},${H}Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[30px] w-24 shrink-0" aria-hidden>
      <path d={area} fill="var(--teal)" opacity=".1" />
      <path d={line} fill="none" stroke="var(--teal)" strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(li)} cy={y(lv)} r="2.75" fill="var(--primary)" stroke="var(--card)" strokeWidth="1.5" />
    </svg>
  );
}

function StatTile({
  label,
  value,
  kpi,
  weeks,
  previous,
  hint,
  trend,
  glass,
}: {
  label: string;
  value: string;
  kpi?: Kpi;
  weeks: number;
  previous?: string;
  hint: string;
  trend?: (number | null)[];
  glass?: boolean;
}) {
  const d = kpi ? delta(kpi, weeks) : null;
  const Arrow = kpi?.change == null || kpi.change === 0 ? ArrowRight : kpi.change > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <section className={cn(glass ? "panel-glass pointer-events-auto" : "panel", "p-4")} title={hint}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="eyebrow">{label}</h2>
          <div className="readout mt-2 text-[30px] font-semibold leading-none">{value}</div>
        </div>
        {trend && <Sparkline values={trend} />}
      </div>
      <div className="mt-2.5 flex items-center gap-1 text-xs text-muted-foreground">
        {d ? (
          <>
            <Arrow className="size-3.5 text-primary" aria-hidden />
            <span>{d}</span>
          </>
        ) : (
          <span>No comparison available</span>
        )}
      </div>
      {previous && <div className="mt-0.5 text-[11px] text-subtle-foreground">Previous: {previous}</div>}
    </section>
  );
}

function KpiTiles({
  data,
  weeks,
  caseBased,
  glass,
}: {
  data: Overview | undefined;
  weeks: number;
  caseBased: boolean;
  glass?: boolean;
}) {
  if (!data) {
    return [0, 1, 2].map((i) => (
      <div key={i} className={cn(glass ? "panel-glass" : "panel", "h-[118px] animate-pulse")} />
    ));
  }
  const k = data.kpis;
  const trend = data.trend;
  if (caseBased || !k.detections || !k.positivity) {
    return <CaseKpiTiles data={data} weeks={weeks} glass={glass} />;
  }
  return (
    <>
      <StatTile
        label="Lab-confirmed detections"
        value={formatCompact(k.detections.value)}
        kpi={k.detections}
        weeks={weeks}
        previous={formatInt(k.detections.previous)}
        hint="Sum of influenza-positive specimens. Depends on testing volume; not a case count."
        trend={trend.map((p) => p.positives)}
        glass={glass}
      />
      <StatTile
        label="Test positivity"
        value={formatPct(k.positivity.value)}
        kpi={k.positivity}
        weeks={weeks}
        previous={formatPct(k.positivity.previous)}
        hint="Positives ÷ specimens tested, pooled over all reporting countries."
        trend={trend.map((p) => p.positivity)}
        glass={glass}
      />
      <StatTile
        label="Countries reporting"
        value={formatInt(k.countries_reporting.value)}
        kpi={k.countries_reporting}
        weeks={weeks}
        previous={formatInt(k.countries_reporting.previous)}
        hint="Countries with at least one week of specimens tested in the period."
        trend={trend.map((p) => p.countries_reporting)}
        glass={glass}
      />
    </>
  );
}

function CaseKpiTiles({ data, weeks, glass }: { data: Overview; weeks: number; glass?: boolean }) {
  const k = data.kpis;
  const trend = data.trend;
  const weekly = k.cases?.denominator;
  const monthly = weekly != null && k.countries_reporting.value != null
    ? k.countries_reporting.value - weekly
    : null;
  return (
    <>
      <StatTile
        label="Reported cases"
        value={formatCompact(k.cases?.value)}
        kpi={k.cases ?? undefined}
        weeks={weeks}
        previous={formatInt(k.cases?.previous)}
        hint={k.cases?.note ?? "Reported cases"}
        trend={trend.map((p) => p.cases ?? null)}
        glass={glass}
      />
      <StatTile
        label="Cases per 100k / week"
        value={formatRate(k.incidence?.value)}
        kpi={k.incidence ?? undefined}
        weeks={weeks}
        previous={formatRate(k.incidence?.previous)}
        hint={k.incidence?.note ?? "Cases per 100,000 per week"}
        trend={trend.map((p) => p.incidence ?? null)}
        glass={glass}
      />
      <StatTile
        label="Countries reporting"
        value={formatInt(k.countries_reporting.value)}
        kpi={k.countries_reporting}
        weeks={weeks}
        previous={formatInt(k.countries_reporting.previous)}
        hint="Countries with a weekly report in the period, or a monthly report overlapping it."
        trend={trend.map((p) => p.countries_reporting)}
        glass={glass}
      />
      {weekly != null && (
        <p className={cn("text-[10.5px] leading-snug text-subtle-foreground", glass && "pointer-events-auto")}>
          Case totals and rates cover the {weekly} weekly-reporting countries
          {monthly ? `; the ${monthly} monthly reporters appear on the map and in Countries` : ""}.
        </p>
      )}
    </>
  );
}

/** Detection signals are influenza-only until phase D4. */
function Signals({ kpis: k, weeks, filters, glass }: {
  kpis: Overview["kpis"];
  weeks: number;
  filters: Filters;
  glass?: boolean;
}) {
  const d = diseaseParam(filters.disease);
  const rows: { key: string; label: string; kpi: Kpi | null; value: string; href: string }[] = [
    {
      key: "anomalies",
      label: "Countries with an anomaly",
      kpi: k.anomalies,
      value: formatInt(k.anomalies?.value),
      href: withParams("/hotspots", d),
    },
    {
      key: "hotspots",
      label: "Countries in a Gi* hot spot",
      kpi: k.hotspots,
      value: formatInt(k.hotspots?.value),
      href: withParams("/hotspots", d),
    },
    {
      key: "above_threshold",
      label: filters.disease === "dengue" ? "Forecast above usual range" : "Forecast above epidemic threshold",
      kpi: k.above_threshold,
      value: k.above_threshold
        ? `${formatInt(k.above_threshold.value)} of ${formatInt(k.above_threshold.denominator)}`
        : "—",
      href: withParams("/surveillance?fill=risk", d),
    },
  ];
  return (
    <section className={cn(glass ? "panel-glass pointer-events-auto" : "panel", "p-4")}>
      <h2 className="eyebrow">Signals</h2>
      <ul className="mt-3 divide-y divide-border/70 text-xs">
        {rows.map((r) => (
          <li key={r.key} title={r.kpi?.note ?? undefined} className="py-2.5 first:pt-0 last:pb-0">
            <Link href={r.href} className="group flex items-center justify-between gap-3">
              <span className="text-muted-foreground group-hover:text-foreground">{r.label}</span>
              <span className="readout shrink-0 text-lg font-semibold text-foreground">
                {r.kpi ? (
                  r.value
                ) : (
                  <span className="font-sans text-xs font-normal text-muted-foreground">No detection run</span>
                )}
              </span>
            </Link>
            {r.kpi && r.kpi.change != null && (
              <div className="text-right text-[10.5px] text-subtle-foreground">
                {formatSigned(r.kpi.change, 0)} vs previous {weeks === 1 ? "week" : `${weeks} weeks`}
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-3 border-t border-border/70 pt-2.5 text-[10.5px] leading-snug text-subtle-foreground">
        Hot spots use the 4 weeks to the window end; the threshold count uses the latest forecast.
      </p>
    </section>
  );
}

/* ---------- Top movers ---------- */

function TopMovers({ data }: { data: Overview | undefined }) {
  return (
    <section className="panel flex flex-col overflow-hidden">
      <header className="border-b border-border p-4 pb-3">
        <h2 className="text-base font-semibold">Largest positivity changes</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {data
            ? `${windowLabel(data.window)} vs ${windowLabel(data.previous_window)} · countries with ≥ ${data.movers_min_specimens} specimens in both periods`
            : "Loading…"}
        </p>
      </header>
      {data && data.top_movers.length === 0 && (
        <p className="p-4 text-xs text-muted-foreground">No country met the minimum testing volume in both periods.</p>
      )}
      {data && data.top_movers.length > 0 && (
        <table className="w-full text-xs">
          <thead className="text-[11px] text-muted-foreground">
            <tr>
              <th className="px-4 py-2 text-left font-normal">Country</th>
              <th className="px-2 py-2 text-right font-normal">Positivity</th>
              <th className="px-2 py-2 text-right font-normal">Change</th>
              <th className="px-4 py-2 text-right font-normal">Specimens</th>
            </tr>
          </thead>
          <tbody className="metric">
            {data.top_movers.map((m) => (
              <tr key={m.iso3} className="border-t border-border/60 hover:bg-accent/40">
                <td className="px-4 py-2">
                  <Link
                    href={`/countries/${m.iso3}`}
                    className="hover:text-primary"
                  >
                    {m.name}
                  </Link>
                </td>
                <td className="px-2 py-2 text-right">
                  {formatPct(m.positivity)}
                  <div className="text-[10.5px] text-muted-foreground">from {formatPct(m.previous_positivity)}</div>
                </td>
                <td className="px-2 py-2 text-right">
                  <span className="inline-flex items-center gap-0.5">
                    {(m.change_pp ?? 0) > 0 ? (
                      <ArrowUpRight className="size-3.5 text-muted-foreground" aria-hidden />
                    ) : (
                      <ArrowDownRight className="size-3.5 text-muted-foreground" aria-hidden />
                    )}
                    {m.change_pp == null ? "—" : formatSigned(m.change_pp, 1, " pp")}
                  </span>
                </td>
                <td className="px-4 py-2 text-right text-muted-foreground">{formatInt(m.specimens_tested)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function TopIncidenceMovers({ data }: { data: Overview | undefined }) {
  return (
    <section className="panel flex flex-col overflow-hidden">
      <header className="border-b border-border p-4 pb-3">
        <h2 className="text-base font-semibold">Largest changes in reported incidence</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {data
            ? `${windowLabel(data.window)} vs ${windowLabel(data.previous_window)} · weekly reporters with ≥ ${data.movers_min_cases ?? 50} cases in both periods`
            : "Loading…"}
        </p>
      </header>
      {data && data.top_movers.length === 0 && (
        <p className="p-4 text-xs text-muted-foreground">No country met the minimum case count in both periods.</p>
      )}
      {data && data.top_movers.length > 0 && (
        <table className="w-full text-xs">
          <thead className="text-[11px] text-muted-foreground">
            <tr>
              <th className="px-4 py-2 text-left font-normal">Country</th>
              <th className="px-2 py-2 text-right font-normal">Per 100k / wk</th>
              <th className="px-2 py-2 text-right font-normal">Change</th>
              <th className="px-4 py-2 text-right font-normal">Cases</th>
            </tr>
          </thead>
          <tbody className="metric">
            {data.top_movers.map((m) => (
              <tr key={m.iso3} className="border-t border-border/60 hover:bg-accent/40">
                <td className="px-4 py-2">
                  <Link href={`/countries/${m.iso3}?disease=dengue`} className="hover:text-primary">
                    {m.name}
                  </Link>
                </td>
                <td className="px-2 py-2 text-right">
                  {formatRate(m.incidence)}
                  <div className="text-[10.5px] text-muted-foreground">from {formatRate(m.previous_incidence)}</div>
                </td>
                <td className="px-2 py-2 text-right">
                  <span className="inline-flex items-center gap-0.5">
                    {(m.change_pct ?? 0) > 0 ? (
                      <ArrowUpRight className="size-3.5 text-muted-foreground" aria-hidden />
                    ) : (
                      <ArrowDownRight className="size-3.5 text-muted-foreground" aria-hidden />
                    )}
                    {m.change_pct == null ? "—" : formatSigned(m.change_pct, 0, "%")}
                  </span>
                </td>
                <td className="px-4 py-2 text-right text-muted-foreground">{formatInt(m.cases)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

/* ---------- Trend ---------- */

interface Metric {
  label: string;
  kind: "line" | "bar";
  get: (p: TrendPoint) => number | null | undefined;
  value: (v: number) => string;
  axis: (v: number) => string;
}

const CASE_METRICS: Record<string, Metric> = {
  cases: {
    label: "Reported cases",
    kind: "bar",
    get: (p) => p.cases,
    value: (v) => formatInt(v),
    axis: (v) => formatCompact(v),
  },
  incidence: {
    label: "Cases per 100k",
    kind: "line",
    get: (p) => p.incidence,
    value: (v) => formatRate(v),
    axis: (v) => formatRate(v),
  },
  countries: {
    label: "Countries reporting",
    kind: "bar",
    get: (p) => p.countries_reporting,
    value: (v) => formatInt(v),
    axis: (v) => formatInt(v),
  },
};

const METRICS: Record<string, Metric> = {
  positivity: {
    label: "Test positivity",
    kind: "line",
    get: (p: TrendPoint) => p.positivity,
    value: (v: number) => formatPct(v),
    axis: (v: number) => `${Math.round(v * 100)}%`,
  },
  positives: {
    label: "Detections",
    kind: "bar",
    get: (p: TrendPoint) => p.positives,
    value: (v: number) => formatInt(v),
    axis: (v: number) => formatCompact(v),
  },
  specimens: {
    label: "Specimens tested",
    kind: "bar",
    get: (p: TrendPoint) => p.specimens_tested,
    value: (v: number) => formatInt(v),
    axis: (v: number) => formatCompact(v),
  },
};

function TrendCard({ data, caseBased }: { data: Overview | undefined; caseBased: boolean }) {
  const metrics = caseBased ? CASE_METRICS : METRICS;
  const [metric, setMetric] = useState<string>(Object.keys(metrics)[0]);
  const m = metrics[metric] ?? Object.values(metrics)[0];
  const points = useMemo<WeeklyPoint[]>(
    () =>
      (data?.trend ?? []).map((p) => ({
        week: p.week_start,
        value: m.get(p) ?? null,
        provisional: p.is_provisional,
        details: [["Countries reporting", formatInt(p.countries_reporting)]],
      })),
    [data, m],
  );

  return (
    <section className="panel flex flex-col p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Weekly {m.label.toLowerCase()}</h2>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {caseBased ? "Weekly-reporting countries" : "Pooled across reporting countries"}
            {data?.region ? ` in ${data.region}` : ""} · selected period highlighted · dashed / faded = provisional (reporting incomplete)
          </p>
        </div>
        <div className="grid grid-cols-3 gap-1 rounded-full border border-border bg-muted p-1 text-xs" role="radiogroup" aria-label="Trend metric">
          {Object.keys(metrics).map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={metric === k}
              onClick={() => setMetric(k)}
              className={cn(
                "rounded-full px-3 py-1 transition-colors",
                metric === k ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {metrics[k].label}
            </button>
          ))}
        </div>
      </header>
      <div className="mt-4 min-h-72 flex-1">
        {data && (
          <WeeklyChart
            points={points}
            kind={m.kind}
            seriesName={m.label}
            formatValue={m.value}
            formatAxis={m.axis}
            highlight={{ start: data.window.start, end: data.window.end }}
            ariaLabel={`Weekly ${m.label.toLowerCase()}, last ${points.length} weeks`}
          />
        )}
      </div>
    </section>
  );
}
