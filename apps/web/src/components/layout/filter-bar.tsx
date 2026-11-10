"use client";

import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { DISEASE_KEYS, DISEASES, isDiseaseKey } from "@/lib/diseases";
import { PERIODS, REGIONS, useFilters } from "@/lib/filters";

function Select({
  id,
  label,
  value,
  onChange,
  children,
  accent = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
  /** The disease selector: amber, the dashboard's primary switch. */
  accent?: boolean;
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
          className={cn(
            "h-8 appearance-none rounded-full border pl-3 pr-8 font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50",
            accent
              ? "border-primary/40 bg-primary/10 text-primary hover:border-primary/70"
              : "border-input bg-card text-foreground hover:border-primary/40",
          )}
        >
          {children}
        </select>
        <ChevronDown
          className={cn(
            "pointer-events-none absolute right-2.5 top-2 size-4",
            accent ? "text-primary" : "text-muted-foreground",
          )}
          aria-hidden
        />
      </span>
    </label>
  );
}

/** Disease, region and period, stored in the URL and shared by every page. */
export function FilterBar() {
  const [filters, setFilters] = useFilters();
  return (
    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
      <Select
        id="filter-disease"
        label="Disease"
        value={filters.disease}
        onChange={(v) => isDiseaseKey(v) && setFilters({ disease: v })}
        accent
      >
        {DISEASE_KEYS.map((k) => (
          <option key={k} value={k}>
            {DISEASES[k].label}
          </option>
        ))}
      </Select>
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
    </div>
  );
}
