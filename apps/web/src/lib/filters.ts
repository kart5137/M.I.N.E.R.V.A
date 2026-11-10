"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

import { DEFAULT_DISEASE, type DiseaseKey, isDiseaseKey } from "@/lib/diseases";

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
  disease: DiseaseKey;
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
    const disease = params.get("disease");
    return {
      disease: isDiseaseKey(disease) ? disease : DEFAULT_DISEASE,
      region: REGIONS.some((r) => r.code === region) ? region : null,
      weeks: (PERIODS as readonly number[]).includes(weeks) ? weeks : DEFAULT_WEEKS,
      to: to && ISO_DATE.test(to) ? to : null,
    };
  }, [params]);

  const update = useCallback((patch: Partial<Filters>) => {
    const next: Record<string, string | number | null | undefined> = { ...patch };
    if ("weeks" in patch) next.weeks = patch.weeks === DEFAULT_WEEKS ? null : patch.weeks;
    if ("disease" in patch) {
      next.disease = patch.disease === DEFAULT_DISEASE ? null : patch.disease;
      // Each disease has its own data range: a chosen end week may not exist for the other.
      if (!("to" in patch)) next.to = null;
    }
    updateSearchParams(next);
  }, []);

  return [filters, update];
}

/** Patch the query string in place; null/undefined/"" removes a key. */
export function updateSearchParams(patch: Record<string, string | number | null | undefined>) {
  const next = new URLSearchParams(window.location.search);
  for (const [k, v] of Object.entries(patch)) {
    if (v == null || v === "") next.delete(k);
    else next.set(k, String(v));
  }
  const qs = next.toString();
  // Next.js syncs native history updates with useSearchParams (no navigation).
  window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

/** The `disease` query parameter for API paths that do not take the full filter set. */
export function diseaseParam(disease: DiseaseKey): string {
  return disease === DEFAULT_DISEASE ? "" : `disease=${disease}`;
}

/** Append query parameters to a path that may already have some. */
export function withParams(path: string, ...params: string[]): string {
  const qs = params.filter(Boolean).join("&");
  if (!qs) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${qs}`;
}

export function filterQuery(f: Filters): string {
  const p = new URLSearchParams({ weeks: String(f.weeks) });
  if (f.disease !== DEFAULT_DISEASE) p.set("disease", f.disease);
  if (f.region) p.set("region", f.region);
  if (f.to) p.set("to", f.to);
  return p.toString();
}

/** The disease selected in the URL (forecasting, detection and intelligence hooks). */
export function useDisease(): DiseaseKey {
  return useFilters()[0].disease;
}

/** `path` with the selected disease appended (nothing for the default disease). */
export function forDisease(path: string, disease: DiseaseKey): string {
  return withParams(path, diseaseParam(disease));
}
