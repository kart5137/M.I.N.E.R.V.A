"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { QueryError } from "@/components/common/query-state";
import { Provenance } from "@/components/common/provenance";
import { WeeklyChart, type WeeklyPoint } from "@/components/charts/weekly-chart";
import { Globe } from "@/components/globe";
import { PageHeader } from "@/components/layout/page-header";
import { AlertListCard } from "@/components/intelligence/alert-list-card";
import { PlatformStatusPanel } from "@/components/overview/platform-status-panel";
import { PositivityLegend } from "@/components/surveillance/positivity-legend";
import { usePlatformStatus } from "@/hooks/use-platform-status";
import { useGlobalSurveillance, useOverview } from "@/hooks/use-surveillance";
import { type Filters, REGIONS, filterQuery, useFilters } from "@/lib/filters";
import { formatCompact, formatInt, formatPct, formatSigned, formatWeek, windowLabel } from "@/lib/format";
import type { Kpi, Overview, TrendPoint } from "@/lib/types";
import { cn } from "@/lib/utils";

export function OverviewDashboard() {
  const platform = usePlatformStatus();
  const [filters, setFilters] = useFilters();
  const overview = useOverview(filters);

  if (platform.kind !== "ready") {
    return (
      <Page description="Global influenza surveillance from WHO FluNet laboratory data.">
        <div className="max-w-md">
          <PlatformStatusPanel />
        </div>
      </Page>
    );
  }
  if (overview.error) {
    return (
      <Page description="Global influenza surveillance from WHO FluNet laboratory data.">
        <QueryError error={overview.error} />
      </Page>
    );
  }
  const data = overview.data;
  const region = REGIONS.find((r) => r.code === filters.region)?.label ?? "All WHO regions";

  return (
    <Page
      description={
        data
          ? `${filters.weeks === 1 ? "1 week" : `${filters.weeks} weeks`} ending ${formatWeek(data.window.end)} · ${region}`
          : "Loading…"
      }
      actions={
        filters.to && (
          <button
            type="button"
            onClick={() => setFilters({ to: null })}
            className="rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
          >
            Back to latest settled week
          </button>
        )
      }
    >
      {data?.window.includes_provisional && <ProvisionalNotice />}
      <KpiStrip data={data} weeks={filters.weeks} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <OverviewGlobe filters={filters} />
        <TopMovers data={data} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <TrendCard data={data} />
        <AlertListCard region={filters.region} to={data?.window.end ?? null} limit={5} />
      </div>
      {data && <Provenance meta={data.meta} />}
    </Page>
  );
}

function Page({
  description,
  actions,
  children,
}: {
  description: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader title="Overview" description={description} actions={actions} />
      {children}
    </div>
  );
}

function ProvisionalNotice() {
  return (
    <div className="flex items-center gap-2 rounded-md border border-status-warn/40 bg-status-warn/10 px-3 py-2 text-xs text-foreground">
      <TriangleAlert className="size-4 shrink-0 text-status-warn" aria-hidden />
      This period includes provisional weeks. Countries are still reporting, so totals will rise.
    </div>
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

function StatTile({
  label,
  value,
  kpi,
  weeks,
  previous,
  hint,
}: {
  label: string;
  value: string;
  kpi?: Kpi;
  weeks: number;
  previous?: string;
  hint: string;
}) {
  const d = kpi ? delta(kpi, weeks) : null;
  const Arrow = kpi?.change == null || kpi.change === 0 ? ArrowRight : kpi.change > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <section className="rounded-lg border border-border bg-card p-4" title={hint}>
      <h2 className="text-xs text-muted-foreground">{label}</h2>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight">{value}</div>
      <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
        {d ? (
          <>
            <Arrow className="size-3.5" aria-hidden />
            <span>{d}</span>
          </>
        ) : (
          <span>No comparison available</span>
        )}
      </div>
      {previous && <div className="mt-0.5 text-[11px] text-muted-foreground/70">Previous: {previous}</div>}
    </section>
  );
}

function KpiStrip({ data, weeks }: { data: Overview | undefined; weeks: number }) {
  if (!data) {
    return <div className="grid h-[116px] animate-pulse rounded-lg border border-border bg-card" />;
  }
  const k = data.kpis;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatTile
        label="Lab-confirmed detections"
        value={formatCompact(k.detections.value)}
        kpi={k.detections}
        weeks={weeks}
        previous={formatInt(k.detections.previous)}
        hint="Sum of influenza-positive specimens. Depends on testing volume; not a case count."
      />
      <StatTile
        label="Test positivity"
        value={formatPct(k.positivity.value)}
        kpi={k.positivity}
        weeks={weeks}
        previous={formatPct(k.positivity.previous)}
        hint="Positives ÷ specimens tested, pooled over all reporting countries."
      />
      <StatTile
        label="Countries reporting"
        value={formatInt(k.countries_reporting.value)}
        kpi={k.countries_reporting}
        weeks={weeks}
        previous={formatInt(k.countries_reporting.previous)}
        hint="Countries with at least one week of specimens tested in the period."
      />
      <Signals kpis={k} weeks={weeks} />
    </div>
  );
}

function Signals({ kpis: k, weeks }: { kpis: Overview["kpis"]; weeks: number }) {
  const rows: { key: string; label: string; kpi: Kpi | null; value: string; href: string }[] = [
    {
      key: "anomalies",
      label: "Countries with an anomaly",
      kpi: k.anomalies,
      value: formatInt(k.anomalies?.value),
      href: "/hotspots",
    },
    {
      key: "hotspots",
      label: "Countries in a Gi* hot spot",
      kpi: k.hotspots,
      value: formatInt(k.hotspots?.value),
      href: "/hotspots",
    },
    {
      key: "above_threshold",
      label: "Forecast above epidemic threshold",
      kpi: k.above_threshold,
      value: k.above_threshold
        ? `${formatInt(k.above_threshold.value)} of ${formatInt(k.above_threshold.denominator)}`
        : "—",
      href: "/surveillance?fill=risk",
    },
  ];
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="text-xs text-muted-foreground">Signals</h2>
      <ul className="mt-2 space-y-2 text-xs">
        {rows.map((r) => (
          <li key={r.key} title={r.kpi?.note ?? undefined}>
            <Link href={r.href} className="flex items-baseline justify-between gap-2 hover:text-foreground">
              <span className="text-muted-foreground">{r.label}</span>
              <span className="metric shrink-0 font-semibold text-foreground">
                {r.kpi ? r.value : <span className="font-normal text-muted-foreground">No detection run</span>}
              </span>
            </Link>
            {r.kpi && r.kpi.change != null && (
              <div className="text-right text-[10.5px] text-muted-foreground">
                {formatSigned(r.kpi.change, 0)} vs previous {weeks === 1 ? "week" : `${weeks} weeks`}
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10.5px] text-muted-foreground/80">
        Hot spots use the 4 weeks to the window end; the threshold count uses the latest forecast.
      </p>
    </section>
  );
}

/* ---------- Globe ---------- */

function OverviewGlobe({ filters }: { filters: Filters }) {
  const global = useGlobalSurveillance(filters);
  const router = useRouter();
  return (
    <section className="relative min-h-[420px] overflow-hidden rounded-lg border border-border xl:min-h-[520px]">
      <Globe
        className="absolute inset-0"
        values={global.data?.countries}
        windowWeeks={global.data?.window.weeks}
        onCountryClick={(c) => router.push(`/surveillance?${filterQuery(filters)}&country=${c.iso3}`)}
      />
      <div className="absolute bottom-3 left-3 w-64 rounded-md border border-border bg-card/90 p-2.5 backdrop-blur">
        <PositivityLegend />
      </div>
      <Link
        href={`/surveillance?${filterQuery(filters)}`}
        className="absolute right-3 top-3 rounded-md border border-border bg-card/90 px-2.5 py-1 text-xs text-muted-foreground backdrop-blur hover:text-foreground"
      >
        Open Global Surveillance →
      </Link>
      {global.error && <QueryError error={global.error} className="absolute left-3 top-3 text-xs text-status-error" />}
    </section>
  );
}

/* ---------- Top movers ---------- */

function TopMovers({ data }: { data: Overview | undefined }) {
  return (
    <section className="flex flex-col rounded-lg border border-border bg-card">
      <header className="border-b border-border p-4 pb-3">
        <h2 className="text-sm font-medium">Largest positivity changes</h2>
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
                    {m.change_pp > 0 ? (
                      <ArrowUpRight className="size-3.5 text-muted-foreground" aria-hidden />
                    ) : (
                      <ArrowDownRight className="size-3.5 text-muted-foreground" aria-hidden />
                    )}
                    {formatSigned(m.change_pp, 1, " pp")}
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

/* ---------- Trend ---------- */

const METRICS = {
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
} as const;
type MetricKey = keyof typeof METRICS;

function TrendCard({ data }: { data: Overview | undefined }) {
  const [metric, setMetric] = useState<MetricKey>("positivity");
  const m = METRICS[metric];
  const points = useMemo<WeeklyPoint[]>(
    () =>
      (data?.trend ?? []).map((p) => ({
        week: p.week_start,
        value: m.get(p),
        provisional: p.is_provisional,
        details: [["Countries reporting", formatInt(p.countries_reporting)]],
      })),
    [data, m],
  );

  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">Weekly {m.label.toLowerCase()}</h2>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Pooled across reporting countries
            {data?.region ? ` in ${data.region}` : ""} · selected period highlighted · dashed / faded = provisional (reporting incomplete)
          </p>
        </div>
        <div className="grid grid-cols-3 gap-1 rounded-md bg-muted p-0.5 text-xs" role="radiogroup" aria-label="Trend metric">
          {(Object.keys(METRICS) as MetricKey[]).map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={metric === k}
              onClick={() => setMetric(k)}
              className={cn(
                "rounded px-2 py-1 transition-colors",
                metric === k ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {METRICS[k].label}
            </button>
          ))}
        </div>
      </header>
      <div className="mt-3 h-64">
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
