"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import { DEFAULT_DISEASE, type DiseaseKey } from "@/lib/diseases";
import { type Filters, diseaseParam, filterQuery, withParams } from "@/lib/filters";
import type {
  CountryWeather,
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

export function useCountryProfile(iso3: string | null, disease: DiseaseKey = DEFAULT_DISEASE) {
  return useQuery({
    queryKey: ["country", iso3, disease],
    queryFn: () => apiGet<CountryProfile>(withParams(`/countries/${iso3}`, diseaseParam(disease))),
    enabled: !!iso3,
    staleTime: STALE,
  });
}

export function useCountries(p: {
  disease?: DiseaseKey;
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
  if (p.disease && p.disease !== DEFAULT_DISEASE) qs.set("disease", p.disease);
  return useQuery({
    queryKey: ["countries", p],
    queryFn: () => apiGet<CountryList>(`/countries?${qs}`),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useCountrySeasons(iso3: string, n = 6, disease: DiseaseKey = DEFAULT_DISEASE) {
  return useQuery({
    queryKey: ["country", iso3, "seasons", n, disease],
    queryFn: () =>
      apiGet<CountrySeasons>(withParams(`/countries/${iso3}/seasons?n=${n}`, diseaseParam(disease))),
    staleTime: STALE,
  });
}

export function useTrends(
  series: string[],
  granularity: Granularity,
  from: string | null,
  disease: DiseaseKey = DEFAULT_DISEASE,
) {
  const qs = new URLSearchParams({ series: series.join(","), granularity, disease });
  if (from) qs.set("from", from);
  return useQuery({
    queryKey: ["analytics", "trends", series, granularity, from, disease],
    queryFn: () => apiGet<Trends>(`/analytics/trends?${qs}`),
    enabled: series.length > 0,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useHeatmap(series: string | null, years: number, disease: DiseaseKey = DEFAULT_DISEASE) {
  return useQuery({
    queryKey: ["analytics", "heatmap", series, years, disease],
    queryFn: () =>
      apiGet<Heatmap>(
        `/analytics/heatmap?series=${encodeURIComponent(series!)}&years=${years}&disease=${disease}`,
      ),
    enabled: !!series,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useCountryTimeseries(
  iso3: string | null,
  from: string,
  to: string,
  disease: DiseaseKey = DEFAULT_DISEASE,
) {
  return useQuery({
    queryKey: ["country", iso3, "timeseries", from, to, disease],
    queryFn: () =>
      apiGet<CountryTimeseries>(
        withParams(`/countries/${iso3}/timeseries?from=${from}&to=${to}`, diseaseParam(disease)),
      ),
    enabled: !!iso3,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

/** Weekly weather at the country's representative point, latest `weeks` weeks. */
/** Weather for an explicit week range (aligned with another series). */
export function useCountryWeatherRange(iso3: string | null, from: string | null, to: string | null) {
  return useQuery({
    queryKey: ["country", iso3, "weather", from, to],
    queryFn: () => apiGet<CountryWeather>(`/countries/${iso3}/weather?from=${from}&to=${to}`),
    enabled: !!iso3 && !!from && !!to,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useCountryWeather(iso3: string | null, weeks: number) {
  return useQuery({
    queryKey: ["country", iso3, "weather", weeks],
    queryFn: () => apiGet<CountryWeather>(`/countries/${iso3}/weather?weeks=${weeks}`),
    enabled: !!iso3,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}
