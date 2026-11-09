"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import { type Filters, filterQuery } from "@/lib/filters";
import type {
  CountryList,
  CountryProfile,
  CountrySeasons,
  CountrySort,
  CountryTimeseries,
  GlobalSurveillance,
  Granularity,
  Heatmap,
  Overview,
  Trends,
} from "@/lib/types";

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

export function useCountries(p: {
  region: string | null;
  q: string;
  sort: CountrySort;
  order: "asc" | "desc";
  page: number;
  pageSize: number;
}) {
  const qs = new URLSearchParams({
    sort: p.sort,
    order: p.order,
    page: String(p.page),
    page_size: String(p.pageSize),
  });
  if (p.region) qs.set("region", p.region);
  if (p.q) qs.set("q", p.q);
  return useQuery({
    queryKey: ["countries", p],
    queryFn: () => apiGet<CountryList>(`/countries?${qs}`),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useCountrySeasons(iso3: string, n = 6) {
  return useQuery({
    queryKey: ["country", iso3, "seasons", n],
    queryFn: () => apiGet<CountrySeasons>(`/countries/${iso3}/seasons?n=${n}`),
    staleTime: STALE,
  });
}

export function useTrends(series: string[], granularity: Granularity, from: string | null) {
  const qs = new URLSearchParams({ series: series.join(","), granularity });
  if (from) qs.set("from", from);
  return useQuery({
    queryKey: ["analytics", "trends", series, granularity, from],
    queryFn: () => apiGet<Trends>(`/analytics/trends?${qs}`),
    enabled: series.length > 0,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useHeatmap(series: string | null, years: number) {
  return useQuery({
    queryKey: ["analytics", "heatmap", series, years],
    queryFn: () =>
      apiGet<Heatmap>(`/analytics/heatmap?series=${encodeURIComponent(series!)}&years=${years}`),
    enabled: !!series,
    placeholderData: keepPreviousData,
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
