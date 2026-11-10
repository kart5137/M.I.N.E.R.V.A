"use client";

/**
 * Country-page sections for case-based diseases (dengue): recent values, weekly and
 * monthly history, and data coverage. Influenza uses the sections in
 * country-intelligence.tsx.
 */

import { ArrowRight, CalendarClock } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { WeeklyChart, type WeeklyPoint } from "@/components/charts/weekly-chart";
import { QueryError } from "@/components/common/query-state";
import { useCountryTimeseries } from "@/hooks/use-surveillance";
import { type DiseaseInfo, FEATURE_LABELS } from "@/lib/diseases";
import { addWeeks, formatCompact, formatInt, formatPct, formatRate, formatWeek, windowLabel } from "@/lib/format";
import { monthSpan } from "@/lib/incidence-scale";
import type { CountryProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

const RANGES = [
  { key: "2y", label: "2 years", weeks: 104 },
  { key: "5y", label: "5 years", weeks: 260 },
  { key: "all", label: "All", weeks: null },
] as const;

/** Mirrors pipeline/src/ei_pipeline/quality/coverage.py DENGUE_TIERS (3-year window). */
const TIER_RULES = {
  A: "forecast-ready (weekly): ≥ 85% of weeks reported, longest gap ≤ 8 weeks, last report ≤ 8 weeks old, cases in ≥ 50% of reported weeks",
  B: "forecast with caution (weekly): ≥ 60% of weeks reported, last report ≤ 26 weeks old, cases in ≥ 50% of reported weeks",
  C: "map and trends only: some data in the 3-year window (all monthly reporters and mostly-zero weekly series)",
  D: "historical only: no data in the 3-year window",
} as const;

function Section({ title, subtitle, actions, children }: {
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

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="panel p-3.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tracking-tight">{value}</div>
      {note && <div className="mt-0.5 text-[11px] text-muted-foreground">{note}</div>}
    </div>
  );
}

export function hasCaseReports(p: CountryProfile): boolean {
  return p.surveillance.weeks_reported > 0 || (p.surveillance.months_reported ?? 0) > 0;
}

export function CaseRecentStats({ p }: { p: CountryProfile }) {
  const r = p.recent;
  const monthly = r?.grain === "month" && r.period_start && r.period_end;
  const lastMonth = p.surveillance.last_reported_month;
  const lastWeek = p.surveillance.last_reported_week;
  const last =
    lastMonth && (!lastWeek || lastMonth > lastWeek) ? monthSpan(lastMonth, lastMonth) : formatWeek(lastWeek);
  return (
    <div>
      <div className="mb-2 text-[11px] text-muted-foreground">{windowLabel(p.recent_window)} (latest settled weeks)</div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Cases per 100k / week"
          value={r ? formatRate(r.incidence) : "No report"}
          note={r && r.incidence == null ? "No population figure: no rate" : undefined}
        />
        <Stat label="Reported cases" value={r ? formatInt(r.cases) : "No report"} />
        <Stat
          label={monthly ? "Monthly report" : "Weeks reported"}
          value={monthly ? monthSpan(r.period_start!, r.period_end!) : `${r?.weeks_reported ?? 0} of ${p.recent_window.weeks}`}
          note={`Last report: ${last}`}
        />
        <Stat
          label="Population"
          value={p.population ? formatCompact(p.population.value) : "Not available"}
          note={p.population ? `World Bank, ${p.population.year}` : undefined}
        />
      </div>
      {monthly && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          This country reports monthly: values cover the calendar months overlapping the period.
        </p>
      )}
    </div>
  );
}

export function CaseHistory({ iso3, p, info }: { iso3: string; p: CountryProfile; info: DiseaseInfo }) {
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("2y");
  const meta = p.meta;
  const weeks = RANGES.find((r) => r.key === range)!.weeks;
  const to = meta.latest_week;
  const from = weeks ? addWeeks(meta.latest_week, -(weeks - 1)) : meta.first_week;
  const series = useCountryTimeseries(iso3, from, to, info.key);

  const { cases, rate, mCases, mRate, hasWeekly } = useMemo(() => {
    const pts = series.data?.points ?? [];
    const months = series.data?.monthly ?? [];
    const w = (get: (s: (typeof pts)[number]) => number | null | undefined, extra: string): WeeklyPoint[] =>
      pts.map((s) => ({
        week: s.week_start,
        value: s.reported ? (get(s) ?? null) : null,
        provisional: s.is_provisional,
        details: [[extra, extra === "Cases" ? formatInt(s.cases) : formatRate(s.incidence)]],
      }));
    const m = (get: (x: (typeof months)[number]) => number | null): WeeklyPoint[] =>
      months.map((x) => ({ week: x.month_start, value: get(x), provisional: x.is_provisional }));
    return {
      cases: w((s) => s.cases, "Per 100k"),
      rate: w((s) => s.incidence, "Cases"),
      mCases: m((x) => x.cases),
      mRate: m((x) => x.incidence),
      hasWeekly: pts.some((s) => s.reported),
    };
  }, [series.data]);

  return (
    <Section
      title="Reported cases over time"
      subtitle="Gaps are periods without a report, never zero · dashed / faded = provisional · case definitions are the country's own"
      actions={
        <div className="grid grid-cols-3 gap-1 rounded-full border border-border bg-muted p-1 text-xs" role="radiogroup" aria-label="History range">
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              role="radio"
              aria-checked={range === r.key}
              onClick={() => setRange(r.key)}
              className={cn(
                "rounded-full px-3 py-1 transition-colors",
                range === r.key ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      }
    >
      {series.error && <QueryError error={series.error} />}
      {series.data && !hasWeekly && mCases.length === 0 && (
        <p className="text-xs text-muted-foreground">No reports in this range.</p>
      )}
      {series.data && hasWeekly && (
        <>
          <h3 className="text-[11px] text-muted-foreground">Weekly reported cases</h3>
          <div className="h-48">
            <WeeklyChart
              points={cases}
              kind="bar"
              seriesName="Cases"
              formatValue={(v) => formatInt(v)}
              formatAxis={(v) => formatCompact(v)}
              ariaLabel={`Weekly reported ${info.label.toLowerCase()} cases`}
            />
          </div>
          <h3 className="mt-3 text-[11px] text-muted-foreground">Cases per 100,000 per week</h3>
          <div className="h-36">
            <WeeklyChart
              compact
              points={rate}
              kind="line"
              seriesName="Per 100k"
              formatValue={(v) => formatRate(v)}
              formatAxis={(v) => formatRate(v)}
              ariaLabel={`Weekly ${info.label.toLowerCase()} cases per 100,000`}
            />
          </div>
        </>
      )}
      {series.data && mCases.length > 0 && (
        <div className={cn(hasWeekly && "mt-4 border-t border-border pt-3")}>
          <h3 className="text-[11px] text-muted-foreground">Monthly reported cases</h3>
          <div className="h-48">
            <WeeklyChart
              period="month"
              points={mCases}
              kind="bar"
              seriesName="Cases"
              formatValue={(v) => formatInt(v)}
              formatAxis={(v) => formatCompact(v)}
              ariaLabel={`Monthly reported ${info.label.toLowerCase()} cases`}
            />
          </div>
          <h3 className="mt-3 text-[11px] text-muted-foreground">Cases per 100,000 per week (monthly average)</h3>
          <div className="h-36">
            <WeeklyChart
              compact
              period="month"
              points={mRate}
              kind="line"
              seriesName="Per 100k / week"
              formatValue={(v) => formatRate(v)}
              formatAxis={(v) => formatRate(v)}
              ariaLabel={`Monthly ${info.label.toLowerCase()} cases per 100,000 per week`}
            />
          </div>
        </div>
      )}
    </Section>
  );
}

export function LaterFeatures({ iso3, info }: { iso3: string; info: DiseaseInfo }) {
  const missing = (Object.keys(info.features) as (keyof DiseaseInfo["features"])[])
    .filter((f) => !info.features[f])
    .map((f) => FEATURE_LABELS[f].toLowerCase());
  return (
    <section className="panel flex flex-wrap items-center justify-between gap-3 p-4">
      <div className="flex items-start gap-3">
        <CalendarClock className="mt-0.5 size-4 shrink-0 text-teal" aria-hidden />
        <div>
          <h2 className="text-sm font-medium">Coming in a later phase for {info.label.toLowerCase()}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {missing.join(", ")}. These are available for influenza today.
          </p>
        </div>
      </div>
      <Link
        href={`/countries/${iso3}`}
        className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:text-foreground"
      >
        Influenza view of this country
        <ArrowRight className="size-3.5" aria-hidden />
      </Link>
    </section>
  );
}

export function CaseCoverage({ p }: { p: CountryProfile }) {
  const c = p.coverage;
  const unit = c?.grain === "month" ? "months" : "weeks";
  const s = p.surveillance;
  const since = [s.first_week, s.first_month].filter(Boolean).sort()[0] ?? null;
  const rows: [string, string][] = [
    ["Reporting since", since ? (since === s.first_month ? monthSpan(since, since) : formatWeek(since)) : "—"],
    ["Weeks reported", formatInt(s.weeks_reported)],
    ["Months reported", formatInt(s.months_reported ?? 0)],
    ...(c
      ? ([
          ["Coverage tier", c.tier],
          ["Profiled in", unit],
          ["Completeness (3 years)", formatPct(c.completeness, 0)],
          ["Longest gap", `${c.longest_gap} ${unit}`],
          ["Weeks since last report", c.weeks_since_last == null ? "—" : String(c.weeks_since_last)],
        ] as [string, string][])
      : []),
  ];
  return (
    <Section title="Data coverage" subtitle={c ? `Profiled at reference week ${formatWeek(c.reference_week)}` : undefined}>
      <dl className="text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b border-border/60 py-1.5 last:border-0">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="metric">{v}</dd>
          </div>
        ))}
      </dl>
      {!c && <p className="mt-2 text-[11px] text-muted-foreground">No coverage profile: no reports to WHO.</p>}
      <ul className="mt-2 space-y-0.5 text-[11px] text-muted-foreground">
        {Object.entries(TIER_RULES).map(([t, rule]) => (
          <li key={t} className={cn(c?.tier === t && "text-foreground")}>
            <span className="font-semibold">{t}</span> — {rule}
          </li>
        ))}
      </ul>
    </Section>
  );
}
