"use client";

import { AnnualCountries } from "@/components/annual/annual-countries";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Provenance } from "@/components/common/provenance";
import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { useCountries } from "@/hooks/use-surveillance";
import { DISEASES, type DiseaseKey } from "@/lib/diseases";
import { REGIONS, diseaseParam, updateSearchParams, useFilters, withParams } from "@/lib/filters";
import { formatInt, formatPct, formatRate, formatWeek, windowLabel } from "@/lib/format";
import { monthSpan } from "@/lib/incidence-scale";
import { MIN_SPECIMENS } from "@/lib/positivity-scale";
import type { CountryListItem, CountrySort } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;
const SORTS: CountrySort[] = ["name", "tier", "positivity", "positives", "specimens_tested", "last_reported_week"];
const CASE_SORTS: CountrySort[] = ["name", "tier", "incidence", "cases"];
/** Numeric columns default to descending (largest first) when first clicked. */
const DESC_FIRST = new Set<CountrySort>([
  "positivity",
  "positives",
  "specimens_tested",
  "last_reported_week",
  "incidence",
  "cases",
]);

export const SEASON_LABEL = { NH: "Northern", SH: "Southern", YR: "Year-round" } as const;

export function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className="inline-grid size-5 place-items-center rounded border border-border text-[10.5px] font-semibold"
      title={`Data-coverage tier ${tier} (A best – D sparse)`}
    >
      {tier}
    </span>
  );
}

export function CountriesTable() {
  const [filters] = useFilters();
  return DISEASES[filters.disease].grain === "year" ? <AnnualCountries /> : <WeeklyCountriesTable />;
}

function WeeklyCountriesTable() {
  const [filters] = useFilters();
  const params = useSearchParams();
  const sortParam = params.get("sort") as CountrySort | null;
  const caseBased = DISEASES[filters.disease].caseBased;
  // Coverage tiers exist where they decide forecast eligibility (influenza, dengue).
  const showTier = DISEASES[filters.disease].features.forecasting;
  const sorts = caseBased ? CASE_SORTS : SORTS;
  const sort: CountrySort = sortParam && sorts.includes(sortParam) ? sortParam : "name";
  const order = params.get("order") === "desc" ? "desc" : "asc";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const q = params.get("q") ?? "";

  // Debounced search box (the URL holds the applied query).
  const [draft, setDraft] = useState(q);
  useEffect(() => {
    if (draft === q) return;
    const t = setTimeout(() => updateSearchParams({ q: draft.trim() || null, page: null }), 250);
    return () => clearTimeout(t);
  }, [draft, q]);

  const list = useCountries({
    disease: filters.disease,
    region: filters.region,
    q,
    sort,
    order,
    page,
    pageSize: PAGE_SIZE,
  });
  const data = list.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const region = REGIONS.find((r) => r.code === filters.region)?.label;

  const setSort = (s: CountrySort) => {
    const nextOrder = s === sort ? (order === "asc" ? "desc" : "asc") : DESC_FIRST.has(s) ? "desc" : "asc";
    updateSearchParams({ sort: s === "name" ? null : s, order: nextOrder === "asc" ? null : nextOrder, page: null });
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="Countries"
        eyebrow={`${DISEASES[filters.disease].label} surveillance`}
        description={
          data
            ? `${formatInt(data.total)} areas${region ? ` in ${region}` : ""} · recent values: ${windowLabel(data.window)}`
            : "Loading…"
        }
        actions={
          <label className="relative block">
            <span className="sr-only">Search countries</span>
            <Search className="pointer-events-none absolute left-2 top-2 size-4 text-muted-foreground" aria-hidden />
            <input
              type="search"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Search name or ISO3"
              className="h-8 w-64 rounded-md border border-border bg-card pl-8 pr-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            />
          </label>
        }
      />

      {list.error && <QueryError error={list.error} />}

      <div
        className="overflow-x-auto panel"
        tabIndex={0}
        role="region"
        aria-label="Countries table"
      >
        <table className="w-full min-w-[820px] text-xs">
          <thead className="text-[11px] text-muted-foreground">
            <tr className="border-b border-border">
              <SortHeader label="Country" k="name" sort={sort} order={order} onSort={setSort} align="left" />
              <th className="px-3 py-2 text-left font-normal">Region</th>
              <th className="px-3 py-2 text-left font-normal">{caseBased ? "Reports" : "Season"}</th>
              {showTier && <SortHeader label="Tier" k="tier" sort={sort} order={order} onSort={setSort} align="center" />}
              {caseBased ? (
                <>
                  <SortHeader label="Per 100k / week" k="incidence" sort={sort} order={order} onSort={setSort} />
                  <SortHeader label="Cases" k="cases" sort={sort} order={order} onSort={setSort} />
                </>
              ) : (
                <>
                  <SortHeader label="Positivity" k="positivity" sort={sort} order={order} onSort={setSort} />
                  <SortHeader label="Detections" k="positives" sort={sort} order={order} onSort={setSort} />
                  <SortHeader label="Specimens" k="specimens_tested" sort={sort} order={order} onSort={setSort} />
                </>
              )}
              {caseBased ? (
                <th className="px-3 py-2 text-right font-normal">Last reported</th>
              ) : (
                <SortHeader label="Last reported" k="last_reported_week" sort={sort} order={order} onSort={setSort} />
              )}
            </tr>
          </thead>
          <tbody className={cn("metric", list.isPlaceholderData && "opacity-60")}>
            {data?.items.map((c) =>
              caseBased ? <CaseRow key={c.iso3} c={c} disease={filters.disease} showTier={showTier} /> : <Row key={c.iso3} c={c} />,
            )}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={showTier ? 8 : 7} className="px-3 py-6 text-center text-muted-foreground">
                  No country matches “{q}”.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>
            {caseBased
              ? "Monthly reporters show the calendar months overlapping the period. Case definitions differ by country. Missing values sort last."
              : `Positivity is shown muted and not ranked when fewer than ${MIN_SPECIMENS} specimens were tested. Missing values sort last.`}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => updateSearchParams({ page: page - 1 === 1 ? null : page - 1 })}
              className="grid size-7 place-items-center rounded-md border border-border hover:text-foreground disabled:opacity-40"
              aria-label="Previous page"
            >
              <ChevronLeft className="size-4" />
            </button>
            <span>
              Page {page} of {pages}
            </span>
            <button
              type="button"
              disabled={page >= pages}
              onClick={() => updateSearchParams({ page: page + 1 })}
              className="grid size-7 place-items-center rounded-md border border-border hover:text-foreground disabled:opacity-40"
              aria-label="Next page"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      )}
      {data && <Provenance meta={data.meta} />}
    </div>
  );
}

function SortHeader({
  label,
  k,
  sort,
  order,
  onSort,
  align = "right",
}: {
  label: string;
  k: CountrySort;
  sort: CountrySort;
  order: "asc" | "desc";
  onSort: (k: CountrySort) => void;
  align?: "left" | "right" | "center";
}) {
  const active = sort === k;
  const Icon = order === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      className={cn("px-3 py-2 font-normal", align === "left" ? "text-left" : align === "center" ? "text-center" : "text-right")}
      aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        onClick={() => onSort(k)}
        className={cn("inline-flex items-center gap-1 hover:text-foreground", active && "text-foreground")}
      >
        {label}
        {active && <Icon className="size-3" aria-hidden />}
      </button>
    </th>
  );
}

function Row({ c }: { c: CountryListItem }) {
  const lowN = c.positivity != null && (c.specimens_tested ?? 0) < MIN_SPECIMENS;
  return (
    <tr className="border-b border-border/60 last:border-0 hover:bg-accent/40">
      <td className="px-3 py-2">
        <Link href={`/countries/${c.iso3}`} className="font-medium hover:text-primary">
          {c.name}
        </Link>
        <span className="ml-2 font-mono text-[10.5px] text-muted-foreground">{c.iso3}</span>
        {!c.has_geometry && (
          <span className="ml-2 text-[10.5px] text-muted-foreground" title="No separate boundary; not drawn on the map">
            not mapped
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-muted-foreground">{c.who_region ?? "—"}</td>
      <td className="px-3 py-2 text-muted-foreground">{c.flu_season ? SEASON_LABEL[c.flu_season] : "—"}</td>
      <td className="px-3 py-2 text-center">
        <TierBadge tier={c.tier} />
      </td>
      <td className={cn("px-3 py-2 text-right", lowN && "text-muted-foreground")} title={lowN ? `Fewer than ${MIN_SPECIMENS} specimens` : undefined}>
        {formatPct(c.positivity)}
        {lowN && "*"}
      </td>
      <td className="px-3 py-2 text-right">{formatInt(c.positives)}</td>
      <td className="px-3 py-2 text-right text-muted-foreground">{formatInt(c.specimens_tested)}</td>
      <td className="px-3 py-2 text-right text-muted-foreground">{formatWeek(c.last_reported_week)}</td>
    </tr>
  );
}

function CaseRow({ c, disease, showTier }: { c: CountryListItem; disease: DiseaseKey; showTier: boolean }) {
  const lastMonth = c.last_reported_month;
  const lastWeek = c.last_reported_week;
  // The more recent of the two report types.
  const last =
    lastMonth && (!lastWeek || lastMonth > lastWeek)
      ? monthSpan(lastMonth, lastMonth)
      : formatWeek(lastWeek);
  const cadence = c.grain ?? (lastMonth && (!lastWeek || lastMonth > lastWeek) ? "month" : lastWeek ? "week" : null);
  return (
    <tr className="border-b border-border/60 last:border-0 hover:bg-accent/40">
      <td className="px-3 py-2">
        <Link href={withParams(`/countries/${c.iso3}`, diseaseParam(disease))} className="font-medium hover:text-primary">
          {c.name}
        </Link>
        <span className="ml-2 font-mono text-[10.5px] text-muted-foreground">{c.iso3}</span>
        {!c.has_geometry && (
          <span className="ml-2 text-[10.5px] text-muted-foreground" title="No separate boundary; not drawn on the map">
            not mapped
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-muted-foreground">{c.who_region ?? "—"}</td>
      <td className="px-3 py-2 text-muted-foreground">
        {cadence === "month" ? "Monthly" : cadence === "week" ? "Weekly" : "—"}
      </td>
      {showTier && (
        <td className="px-3 py-2 text-center">
        <TierBadge tier={c.tier} />
      </td>
      )}
      <td className="px-3 py-2 text-right">{formatRate(c.incidence)}</td>
      <td className="px-3 py-2 text-right">{formatInt(c.cases)}</td>
      <td className="px-3 py-2 text-right text-muted-foreground">{last}</td>
    </tr>
  );
}
