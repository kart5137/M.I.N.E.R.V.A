"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { useAnnualCountries } from "@/hooks/use-annual";
import { formatAnnualRate, formatCount, withRange, yearChange } from "@/lib/annual-scale";
import { DISEASES } from "@/lib/diseases";
import { REGIONS, diseaseParam, useFilters, withParams } from "@/lib/filters";
import { formatInt, formatSigned } from "@/lib/format";
import type { AnnualCountry } from "@/lib/types";
import { cn } from "@/lib/utils";

type SortKey = "name" | "est_cases" | "est_incidence" | "est_deaths" | "reported_cases" | "change";

const COLS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: "name", label: "Country", numeric: false },
  { key: "est_cases", label: "Estimated cases (range)", numeric: true },
  { key: "est_incidence", label: "Per 1,000 at risk", numeric: true },
  { key: "est_deaths", label: "Estimated deaths", numeric: true },
  { key: "reported_cases", label: "Reported cases", numeric: true },
  { key: "change", label: "Estimated cases vs previous year", numeric: true },
];

function sortValue(c: AnnualCountry, k: SortKey): number | string | null {
  if (k === "name") return c.name;
  if (k === "change") return yearChange(c.values.est_cases, c.previous.est_cases);
  return c.values[k]?.value ?? null;
}

/** Countries table for yearly diseases (malaria). */
export function AnnualCountries() {
  const [filters] = useFilters();
  const info = DISEASES[filters.disease];
  const q = useAnnualCountries(filters.disease, filters.year, filters.region);
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "est_cases", desc: true });
  const region = REGIONS.find((r) => r.code === filters.region)?.label ?? "All WHO regions";

  const rows = useMemo(() => {
    const items = (q.data?.items ?? []).filter((c) => Object.keys(c.values).length > 0);
    return items.sort((a, b) => {
      const x = sortValue(a, sort.key);
      const y = sortValue(b, sort.key);
      if (x == null && y == null) return a.name.localeCompare(b.name);
      if (x == null) return 1;
      if (y == null) return -1;
      const c = typeof x === "string" ? x.localeCompare(String(y)) : x - (y as number);
      return sort.desc ? -c : c;
    });
  }, [q.data, sort]);

  const dq = diseaseParam(filters.disease);
  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="Countries"
        eyebrow={`${info.label} · yearly estimates`}
        description={q.data ? `${q.data.year} · ${region} · ${rows.length} countries with malaria data` : "Loading…"}
      />
      {q.error && <QueryError error={q.error} />}
      <section className="panel overflow-x-auto p-0" tabIndex={0} role="region" aria-label="Malaria by country">
        <table className="w-full min-w-[820px] text-xs">
          <thead className="text-[11px] text-muted-foreground">
            <tr className="border-b border-border">
              {COLS.map((c) => (
                <th
                  key={c.key}
                  className={cn("px-3 py-2 font-normal", c.numeric ? "text-right" : "text-left")}
                  aria-sort={sort.key === c.key ? (sort.desc ? "descending" : "ascending") : "none"}
                >
                  <button
                    type="button"
                    onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : c.numeric }))}
                    className="hover:text-foreground"
                  >
                    {c.label}
                    {sort.key === c.key ? (sort.desc ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="metric">
            {rows.map((c) => {
              const ch = yearChange(c.values.est_cases, c.previous.est_cases);
              return (
                <tr key={c.iso3} className="border-b border-border/60 last:border-0 hover:bg-accent/30">
                  <td className="px-3 py-1.5">
                    <Link href={withParams(`/countries/${c.iso3}`, dq, filters.year ? `year=${filters.year}` : "")} className="hover:text-primary">
                      {c.name}
                    </Link>
                    <span className="ml-1.5 text-[10px] text-muted-foreground">{c.who_region}</span>
                  </td>
                  <td className="px-3 py-1.5 text-right">{withRange(c.values.est_cases, formatCount)}</td>
                  <td className="px-3 py-1.5 text-right">{formatAnnualRate(c.values.est_incidence?.value)}</td>
                  <td className="px-3 py-1.5 text-right">{withRange(c.values.est_deaths, formatCount)}</td>
                  <td className="px-3 py-1.5 text-right">
                    {c.values.reported_cases ? formatInt(c.values.reported_cases.value) : <span className="text-muted-foreground">Not reported</span>}
                  </td>
                  <td className="px-3 py-1.5 text-right">{ch == null ? "—" : formatSigned(ch, 1, "%")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      <p className="text-[11px] text-muted-foreground">
        Estimates are WHO World Malaria Report model results; reported cases are what national programmes reported and
        differ from estimates, often widely. Ranges are WHO&apos;s uncertainty intervals.
      </p>
    </div>
  );
}
