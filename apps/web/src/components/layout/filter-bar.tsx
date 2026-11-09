"use client";

import { ChevronDown } from "lucide-react";

import { PERIODS, REGIONS, useFilters } from "@/lib/filters";

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
      <span className="hidden text-muted-foreground sm:inline">{label}</span>
      <span className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-7 appearance-none rounded-md border border-border bg-card pl-2 pr-7 font-medium text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-1.5 top-1.5 size-4 text-muted-foreground" aria-hidden />
      </span>
    </label>
  );
}

/** Region and period filters, stored in the URL and shared by every surveillance page. */
export function FilterBar() {
  const [filters, setFilters] = useFilters();
  return (
    <div className="flex items-center gap-3">
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
