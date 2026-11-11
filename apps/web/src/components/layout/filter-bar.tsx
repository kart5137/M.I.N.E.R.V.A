"use client";

import { ChevronDown } from "lucide-react";

import { useAnnualSummary } from "@/hooks/use-annual";
import { DISEASES } from "@/lib/diseases";
import { PERIODS, REGIONS, useFilters } from "@/lib/filters";

import { DiseaseSelect } from "./disease-select";

function Select({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-xs">
      {/* Visible from sm up; always present for screen readers. */}
      <span className="eyebrow sr-only sm:not-sr-only">{label}</span>
      <span className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 appearance-none rounded-full border border-input bg-card pl-3 pr-8 font-medium text-foreground outline-none transition-colors hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-2 size-4 text-muted-foreground" aria-hidden />
      </span>
    </label>
  );
}

/** Disease, region and period (or year, for yearly diseases), stored in the URL and shared
 *  by every page. */
export function FilterBar() {
  const [filters, setFilters] = useFilters();
  const yearly = DISEASES[filters.disease].grain === "year";
  const summary = useAnnualSummary(filters.disease, null, yearly);
  const years = summary.data?.years ?? [];
  return (
    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
      <DiseaseSelect value={filters.disease} onChange={(v) => setFilters({ disease: v })} />
      <Select
        id="filter-region"
        label="Region"
        value={filters.region ?? ""}
        onChange={(v) => setFilters({ region: v || null })}
      >
        <option value="">All WHO regions</option>
        {REGIONS.map((r) => (
          <option key={r.code} value={r.code}>
            {r.label} ({r.code})
          </option>
        ))}
      </Select>
      {yearly ? (
        <Select
          id="filter-year"
          label="Year"
          value={String(filters.year ?? summary.data?.meta.latest_year ?? "")}
          onChange={(v) => setFilters({ year: Number(v) === summary.data?.meta.latest_year ? null : Number(v) })}
        >
          {years.length === 0 && <option value="">Latest</option>}
          {[...years].reverse().map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </Select>
      ) : (
        <Select
          id="filter-period"
          label="Period"
          value={String(filters.weeks)}
          onChange={(v) => setFilters({ weeks: Number(v) })}
        >
          {PERIODS.map((w) => (
            <option key={w} value={w}>
              {w === 1 ? "1 week" : `${w} weeks`}
            </option>
          ))}
        </Select>
      )}
    </div>
  );
}
