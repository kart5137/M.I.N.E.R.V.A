"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

/**
 * Dashboard filters live in the URL query string, so every view is shareable and
 * back-button safe. Components using this must sit under a <Suspense> boundary.
 */
export const REGIONS = [
  { code: "AFR", label: "Africa" },
  { code: "AMR", label: "Americas" },
  { code: "EMR", label: "Eastern Mediterranean" },
  { code: "EUR", label: "Europe" },
  { code: "SEAR", label: "South-East Asia" },
  { code: "WPR", label: "Western Pacific" },
] as const;

export const PERIODS = [1, 4, 8, 13, 26, 52] as const;
export const DEFAULT_WEEKS = 4;

export interface Filters {
  region: string | null;
  weeks: number;
  /** Last week of the window; null = the reference week. */
  to: string | null;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function useFilters(): [Filters, (patch: Partial<Filters>) => void] {
  const params = useSearchParams();

  const filters = useMemo<Filters>(() => {
    const region = params.get("region")?.toUpperCase() ?? null;
    const weeks = Number(params.get("weeks"));
    const to = params.get("to");
    return {
      region: REGIONS.some((r) => r.code === region) ? region : null,
      weeks: (PERIODS as readonly number[]).includes(weeks) ? weeks : DEFAULT_WEEKS,
      to: to && ISO_DATE.test(to) ? to : null,
    };
  }, [params]);

  const update = useCallback((patch: Partial<Filters>) => {
    const next = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(patch)) {
      if (v == null || (k === "weeks" && v === DEFAULT_WEEKS)) next.delete(k);
      else next.set(k, String(v));
    }
    const qs = next.toString();
    // Next.js syncs native history updates with useSearchParams (no navigation).
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, []);

  return [filters, update];
}

export function filterQuery(f: Filters): string {
  const p = new URLSearchParams({ weeks: String(f.weeks) });
  if (f.region) p.set("region", f.region);
  if (f.to) p.set("to", f.to);
  return p.toString();
}
