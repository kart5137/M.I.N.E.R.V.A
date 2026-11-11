"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import type { DiseaseKey } from "@/lib/diseases";
import { withParams } from "@/lib/filters";
import type { AnnualCountries, AnnualSeries, AnnualSummary } from "@/lib/types";

const STALE = 30 * 60_000; // yearly data changes at most once a week

function q(disease: DiseaseKey, ...more: (string | null | undefined | false)[]): string {
  return [`disease=${disease}`, ...more.filter(Boolean)].join("&");
}

export function useAnnualSummary(disease: DiseaseKey, year: number | null, enabled = true) {
  return useQuery({
    queryKey: ["annual", disease, "summary", year],
    queryFn: () => apiGet<AnnualSummary>(withParams("/annual/summary", q(disease, year != null && `year=${year}`))),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useAnnualCountries(disease: DiseaseKey, year: number | null, region: string | null) {
  return useQuery({
    queryKey: ["annual", disease, "countries", year, region],
    queryFn: () =>
      apiGet<AnnualCountries>(
        withParams("/annual/countries", q(disease, year != null && `year=${year}`, region && `region=${region}`)),
      ),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useAnnualSeries(disease: DiseaseKey, area: string | null) {
  return useQuery({
    queryKey: ["annual", disease, "series", area],
    queryFn: () => apiGet<AnnualSeries>(withParams("/annual/series", q(disease, `area=${area}`))),
    enabled: !!area,
    staleTime: STALE,
  });
}
