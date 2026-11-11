"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight, Info } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

import { QueryError } from "@/components/common/query-state";
import { Globe } from "@/components/globe";
import { annualElevation } from "@/components/globe/elevation";
import { useAnnualCountries, useAnnualSeries, useAnnualSummary } from "@/hooks/use-annual";
import { useMediaQuery } from "@/hooks/use-element-size";
import {
  formatAnnualRate,
  formatCount,
  MALARIA_BINS,
  MALARIA_FILL_COLORS,
  malariaClass,
  withRange,
  yearChange,
  ZERO_COLOR,
} from "@/lib/annual-scale";
import { DISEASES } from "@/lib/diseases";
import { REGIONS, diseaseParam, useFilters, withParams } from "@/lib/filters";
import { formatInt, formatSigned } from "@/lib/format";
import type { AnnualCountry, AreaTotal, MeasureValue } from "@/lib/types";
import { cn } from "@/lib/utils";

import { AnnualBandChart } from "./annual-chart";

const CTA =
  "pointer-events-auto inline-flex items-center justify-center gap-1.5 rounded-full bg-primary font-semibold text-primary-foreground shadow-[0_8px_24px_-8px_rgba(242,169,59,0.6)] transition-colors hover:bg-primary/90";
const REGION_LABEL = Object.fromEntries(REGIONS.map((r) => [r.code, r.label]));

function Change({ cur, prev, year }: { cur?: MeasureValue; prev?: MeasureValue; year: number }) {
  const c = yearChange(cur, prev);
  if (c == null) return <span>No comparison with {year - 1}</span>;
  const Arrow = c === 0 ? ArrowRight : c > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <>
      <Arrow className="size-3.5 text-primary" aria-hidden />
      <span>
        {formatSigned(c, 1, "%")} vs {year - 1}
      </span>
    </>
  );
}

function Tile({ label, value, range, change, hint }: {
  label: string;
  value: string;
  range?: string | null;
  change: React.ReactNode;
  hint: string;
}) {
  return (
    <section className="panel-glass pointer-events-auto p-4" title={hint}>
      <h2 className="eyebrow">{label}</h2>
      <div className="readout mt-2 text-[28px] font-semibold leading-none">{value}</div>
      {range && <div className="mt-1 text-[11px] text-subtle-foreground">Range {range}</div>}
      <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">{change}</div>
    </section>
  );
}

function Tiles({ world, year, countries }: { world: AreaTotal | null; year: number; countries: string }) {
  const v = world?.values ?? {};
  const p = world?.previous ?? {};
  const range = (m?: MeasureValue, f = formatCount) => (m?.low != null && m?.high != null ? `${f(m.low)}–${f(m.high)}` : null);
  return (
    <>
      <Tile
        label="Estimated cases"
        value={formatCount(v.est_cases?.value)}
        range={range(v.est_cases)}
        change={<Change cur={v.est_cases} prev={p.est_cases} year={year} />}
        hint="World Malaria Report estimate for the year, with WHO's uncertainty range"
      />
      <Tile
        label="Estimated deaths"
        value={formatCount(v.est_deaths?.value)}
        range={range(v.est_deaths)}
        change={<Change cur={v.est_deaths} prev={p.est_deaths} year={year} />}
        hint="World Malaria Report estimate for the year, with WHO's uncertainty range"
      />
      <Tile
        label="Cases per 1,000 at risk"
        value={formatAnnualRate(v.est_incidence?.value)}
        range={range(v.est_incidence, formatAnnualRate)}
        change={<span>{countries}</span>}
        hint="Estimated cases per 1,000 population at risk of malaria"
      />
    </>
  );
}

function Regions({ regions, world, year }: { regions: AreaTotal[]; world: AreaTotal | null; year: number }) {
  const total = world?.values.est_cases?.value ?? 0;
  const rows = [...regions].sort((a, b) => (b.values.est_cases?.value ?? 0) - (a.values.est_cases?.value ?? 0));
  return (
    <section className="panel-glass pointer-events-auto p-4">
      <h2 className="eyebrow">Estimated cases by WHO region, {year}</h2>
      <ul className="mt-3 space-y-2 text-xs">
        {rows.map((r) => {
          const v = r.values.est_cases?.value ?? 0;
          const share = total ? v / total : 0;
          return (
            <li key={r.area}>
              <div className="flex items-baseline justify-between gap-2">
                <span>{REGION_LABEL[r.area] ?? r.area}</span>
                <span className="metric">
                  {formatCount(v)} <span className="text-muted-foreground">({(share * 100).toFixed(share < 0.01 && share > 0 ? 1 : 0)}%)</span>
                </span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-muted">
                <div className="h-1.5 rounded-full bg-primary/80" style={{ width: `${Math.max(share * 100, share > 0 ? 1 : 0)}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-[10.5px] leading-snug text-muted-foreground">
        Regional and world totals are WHO&apos;s own estimates; their ranges are not sums of countries.
      </p>
    </section>
  );
}

export function MalariaLegend({ className }: { className?: string }) {
  return (
    <figure className={cn("space-y-2 text-[11px]", className)} aria-label="Map legend">
      <figcaption className="font-medium text-foreground">Estimated malaria cases per 1,000 at risk</figcaption>
      <div className="flex">
        {MALARIA_BINS.map((b) => (
          <div key={b.label} className="flex-1">
            <div className="h-2.5 border-r-2 border-card last:border-r-0" style={{ background: b.color }} />
            <div className="metric mt-1 text-center text-[10px] text-muted-foreground">{b.label}</div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px]" style={{ background: ZERO_COLOR }} />
          Zero (no indigenous cases)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] border border-[var(--globe-border)] bg-[var(--globe-land)]" />
          No estimate
        </span>
      </div>
      <p className="text-[10.5px] leading-snug text-muted-foreground">Country height ∝ √ estimated cases (capped at 70 million a year).</p>
    </figure>
  );
}

function hoverRows(c: AnnualCountry | undefined, year: number) {
  if (!c) return <div className="mt-1 text-muted-foreground">No malaria estimate for {year}</div>;
  const v = c.values;
  const rows: [string, string][] = [
    ["Estimated cases", withRange(v.est_cases, formatCount)],
    ["Per 1,000 at risk", formatAnnualRate(v.est_incidence?.value)],
    ["Estimated deaths", withRange(v.est_deaths, formatCount)],
    ["Reported cases", v.reported_cases ? formatInt(v.reported_cases.value) : "Not reported"],
  ];
  return (
    <div className="mt-1.5 space-y-0.5">
      {rows.map(([k, val]) => (
        <div key={k} className="flex justify-between gap-4">
          <span className="text-muted-foreground">{k}</span>
          <span className="metric text-foreground">{val}</span>
        </div>
      ))}
    </div>
  );
}

/** Overview for yearly diseases (malaria): world map and totals for the selected year. */
export function AnnualOverview() {
  const [filters] = useFilters();
  const info = DISEASES[filters.disease];
  const summary = useAnnualSummary(filters.disease, filters.year);
  const year = summary.data?.year ?? filters.year;
  const countries = useAnnualCountries(filters.disease, year ?? null, null);
  const world = useAnnualSeries(filters.disease, "GLOBAL");
  const router = useRouter();
  const lg = useMediaQuery("(min-width: 1024px)");
  const xl = useMediaQuery("(min-width: 1280px)");
  const insets = { top: lg ? 0 : 96, left: lg ? 320 : 0, right: xl ? 344 : 0, bottom: lg ? 0 : 88 };

  const byIso3 = useMemo(() => new Map((countries.data?.items ?? []).map((c) => [c.iso3, c])), [countries.data]);
  const fill = useMemo(
    () => ({
      byIso3: new Map([...byIso3].map(([iso3, c]) => [iso3, malariaClass(c.values)] as [string, number]).filter(([, k]) => k >= 0)),
      colors: MALARIA_FILL_COLORS,
    }),
    [byIso3],
  );
  const elevation = useMemo(
    () => new Map([...byIso3].map(([iso3, c]) => [iso3, annualElevation(c.values.est_cases?.value)])),
    [byIso3],
  );
  const trend = (world.data?.points ?? []).map((p) => p.values.est_cases?.value ?? null);
  const d = summary.data;
  const dq = diseaseParam(filters.disease);
  const countriesHref = withParams("/countries", dq, filters.year ? `year=${filters.year}` : "");

  return (
    <div className="flex flex-1 flex-col">
      <section
        aria-label="Global picture"
        className="relative h-[600px] overflow-hidden border-b border-border/70 lg:h-[clamp(640px,calc(100dvh-104px),880px)]"
      >
        <Globe
          className="absolute inset-0"
          insets={insets}
          fill={fill}
          elevationByIso3={elevation}
          pitch={12}
          clouds
          hoverDetail={(iso3) => hoverRows(byIso3.get(iso3), year ?? 0)}
          onCountryClick={(c) => router.push(withParams(`/countries/${c.iso3}`, dq, filters.year ? `year=${filters.year}` : ""))}
        />
        <div
          className="pointer-events-none absolute inset-0"
          style={{ background: "linear-gradient(90deg, rgb(3 11 13 / 0.7) 0%, transparent 30%, transparent 72%, rgb(3 11 13 / 0.55) 100%)" }}
          aria-hidden
        />
        <div className="pointer-events-none absolute inset-0 flex flex-col gap-4 p-4 lg:p-6">
          <div className="flex items-start justify-between gap-3">
            <div className="pointer-events-auto max-w-sm">
              <div className="eyebrow text-teal">{info.label} · yearly estimates</div>
              <h1 className="mt-1.5 text-2xl font-semibold tracking-tight lg:text-[30px]">Global overview</h1>
              <p className="mt-1 text-[13px] text-muted-foreground">
                {d ? `${d.year} · WHO World Malaria Report estimates and reported cases` : "Loading…"}
              </p>
            </div>
            <Link href={countriesHref} className={cn(CTA, "h-9 px-4 text-xs xl:hidden")}>
              Countries <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
          <div className="flex min-h-0 flex-1 gap-4">
            <div className="hidden w-[280px] flex-col gap-3 lg:flex">
              {d ? (
                <Tiles
                  world={d.world}
                  year={d.year}
                  countries={`${formatInt(d.countries_with_estimates)} countries with estimates · ${formatInt(d.countries_reporting)} reporting cases`}
                />
              ) : (
                [0, 1, 2].map((i) => <div key={i} className="panel-glass h-[118px] animate-pulse" />)
              )}
            </div>
            <div className="flex-1" />
            <div className="hidden w-[320px] flex-col gap-3 xl:flex">
              {d && <Regions regions={d.regions} world={d.world} year={d.year} />}
              <Link href={countriesHref} className={cn(CTA, "h-10 px-4 text-[13px]")}>
                All countries, {d?.year ?? ""} <ArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
          </div>
          <div className="flex items-end justify-between gap-3">
            <div className="panel-glass pointer-events-auto w-72 rounded-xl p-3 lg:ml-[296px]">
              <MalariaLegend />
            </div>
            {(summary.error || countries.error) && (
              <QueryError error={(summary.error ?? countries.error) as Error} className="pointer-events-auto text-xs text-status-error" />
            )}
          </div>
        </div>
      </section>

      <div className="flex flex-col gap-4 p-4 lg:p-6">
        <div className="grid gap-3 sm:grid-cols-3 lg:hidden">
          {d && <Tiles world={d.world} year={d.year} countries={`${formatInt(d.countries_with_estimates)} countries with estimates`} />}
        </div>
        {d && (
          <div className="xl:hidden">
            <Regions regions={d.regions} world={d.world} year={d.year} />
          </div>
        )}
        <WorldTrend points={world.data?.points ?? []} year={d?.year ?? null} trend={trend} />
        {d && (
          <section className="panel flex items-start gap-3 p-4 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-4 shrink-0 text-teal" aria-hidden />
            <ul className="space-y-1">
              {d.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
              <li>
                Source: {d.meta.sources.map((s) => s.attribution ?? s.name).join(" · ")} Years {d.meta.first_year}–
                {d.meta.latest_year}.
              </li>
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

function WorldTrend({ points, year, trend }: {
  points: { year: number; values: Record<string, MeasureValue | undefined> }[];
  year: number | null;
  trend: (number | null)[];
}) {
  if (!points.length || trend.every((v) => v == null)) return null;
  return (
    <section className="panel p-4">
      <h2 className="text-sm font-medium">World: estimated malaria cases and deaths by year</h2>
      <p className="mt-0.5 text-[11px] text-muted-foreground">WHO World Malaria Report estimates; shaded: uncertainty range. {year ? `${year} highlighted.` : ""}</p>
      <div className="mt-2 grid gap-4 lg:grid-cols-2">
        <div className="h-56">
          <AnnualBandChart points={points} measure="est_cases" label="Estimated cases" highlight={year} />
        </div>
        <div className="h-56">
          <AnnualBandChart points={points} measure="est_deaths" label="Estimated deaths" highlight={year} />
        </div>
      </div>
    </section>
  );
}

