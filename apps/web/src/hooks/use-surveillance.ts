"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import { type Filters, filterQuery } from "@/lib/filters";
import type { CountryProfile, CountryTimeseries, GlobalSurveillance, Overview } from "@/lib/types";

const STALE = 5 * 60_000;

export function useOverview(f: Filters) {
  return useQuery({
    queryKey: ["overview", f],
    queryFn: () => apiGet<Overview>(`/overview?${filterQuery(f)}`),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function globalQueryOptions(f: Filters) {
  return {
    queryKey: ["surveillance", "global", f] as const,
    queryFn: () => apiGet<GlobalSurveillance>(`/surveillance/global?${filterQuery(f)}`),
    staleTime: STALE,
  };
}

export function useGlobalSurveillance(f: Filters) {
  return useQuery({ ...globalQueryOptions(f), placeholderData: keepPreviousData });
}

export function useCountryProfile(iso3: string | null) {
  return useQuery({
    queryKey: ["country", iso3],
    queryFn: () => apiGet<CountryProfile>(`/countries/${iso3}`),
    enabled: !!iso3,
    staleTime: STALE,
  });
}

export function useCountryTimeseries(iso3: string | null, from: string, to: string) {
  return useQuery({
    queryKey: ["country", iso3, "timeseries", from, to],
    queryFn: () => apiGet<CountryTimeseries>(`/countries/${iso3}/timeseries?from=${from}&to=${to}`),
    enabled: !!iso3,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}
