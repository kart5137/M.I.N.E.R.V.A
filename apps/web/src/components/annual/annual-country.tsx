"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { useAnnualSeries } from "@/hooks/use-annual";
import { formatAnnualRate, formatCount, withRange, yearChange } from "@/lib/annual-scale";
import { DISEASES } from "@/lib/diseases";
import { diseaseParam, useFilters, withParams } from "@/lib/filters";
import { formatInt, formatSigned } from "@/lib/format";

import { AnnualBandChart } from "./annual-chart";

/** Country page for yearly diseases (malaria): estimates with ranges and reported cases. */
export function AnnualCountryView({ iso3 }: { iso3: string }) {
  const [filters] = useFilters();
  const info = DISEASES[filters.disease];
  const q = useAnnualSeries(filters.disease, iso3.toUpperCase());
  const d = q.data;
  const pts = d?.points ?? [];
  const latest = pts.at(-1);
  const prev = pts.at(-2);
  const dq = diseaseParam(filters.disease);
  const hasData = pts.length > 0;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <Link href={withParams("/countries", dq)} className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" aria-hidden /> Countries
      </Link>
      <PageHeader
        title={d?.name ?? iso3.toUpperCase()}
        eyebrow={`${info.label} · yearly estimates`}
        description={
          !d ? "Loading…" : hasData ? `${pts[0].year}–${latest!.year} · WHO World Malaria Report` : "No malaria data for this country"
        }
      />
      {q.error && <QueryError error={q.error} />}
      {d && !hasData && (
        <p className="panel p-4 text-xs text-muted-foreground">
          WHO publishes no malaria estimates or reported cases for this country (it is not, or no longer, malaria-endemic).
        </p>
      )}
      {latest && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Estimated cases", withRange(latest.values.est_cases, formatCount), latest.values.est_cases, prev?.values.est_cases],
            ["Estimated deaths", withRange(latest.values.est_deaths, formatCount), latest.values.est_deaths, prev?.values.est_deaths],
            ["Cases per 1,000 at risk", withRange(latest.values.est_incidence, formatAnnualRate), latest.values.est_incidence, prev?.values.est_incidence],
            ["Reported cases", latest.values.reported_cases ? formatInt(latest.values.reported_cases.value) : "Not reported", latest.values.reported_cases, prev?.values.reported_cases],
          ].map(([label, value, cur, before]) => {
            const ch = yearChange(cur as never, before as never);
            return (
              <section key={label as string} className="panel p-4">
                <h2 className="eyebrow">{label as string}, {latest.year}</h2>
                <div className="readout mt-2 text-lg font-semibold">{value as string}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {ch == null ? `No comparison with ${latest.year - 1}` : `${formatSigned(ch, 1, "%")} vs ${latest.year - 1}`}
                </div>
              </section>
            );
          })}
        </div>
      )}
      {hasData && (
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="panel p-4">
            <h2 className="text-sm font-medium">Cases by year</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Estimated cases with WHO&apos;s uncertainty range (shaded), and cases the national programme reported. Where
              they differ, testing and reporting reach only part of the cases.
            </p>
            <div className="mt-2 h-64">
              <AnnualBandChart points={pts} measure="est_cases" label="Estimated cases" reported highlight={filters.year} />
            </div>
          </section>
          <section className="panel p-4">
            <h2 className="text-sm font-medium">Estimated cases per 1,000 population at risk</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">Shaded: uncertainty range.</p>
            <div className="mt-2 h-64">
              <AnnualBandChart points={pts} measure="est_incidence" label="Per 1,000 at risk" rate highlight={filters.year} />
            </div>
          </section>
          <section className="panel p-4 xl:col-span-2">
            <h2 className="text-sm font-medium">Estimated deaths by year</h2>
            <div className="mt-2 h-56">
              <AnnualBandChart points={pts} measure="est_deaths" label="Estimated deaths" highlight={filters.year} />
            </div>
          </section>
        </div>
      )}
      {d && (
        <p className="text-[11px] text-muted-foreground">
          Source: {d.meta.sources.map((s) => s.attribution ?? s.name).join(" · ")} Estimates are revised by WHO every year.
        </p>
      )}
    </div>
  );
}
