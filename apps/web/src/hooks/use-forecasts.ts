"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import { forDisease, useDisease } from "@/lib/filters";
import type { CountryBacktest, CountryForecasts, Explanation, ModelDetail, ModelRun } from "@/lib/types";

const STALE = 5 * 60_000;

export function useModelRun() {
  const disease = useDisease();
  return useQuery({
    queryKey: ["models", disease],
    queryFn: () => apiGet<ModelRun>(forDisease("/models", disease)),
    staleTime: STALE,
  });
}

export function useModelDetail(id: number | null) {
  const disease = useDisease();
  return useQuery({
    queryKey: ["models", disease, id],
    queryFn: () => apiGet<ModelDetail>(forDisease(`/models/${id}`, disease)),
    enabled: id != null,
    staleTime: STALE,
  });
}

export function useCountryForecasts(iso3: string | null) {
  const disease = useDisease();
  return useQuery({
    queryKey: ["forecasts", disease, iso3],
    queryFn: () => apiGet<CountryForecasts>(forDisease(`/forecasts?iso3=${iso3}`, disease)),
    enabled: !!iso3,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useExplanation(forecastId: number | null) {
  return useQuery({
    queryKey: ["explanation", forecastId],
    queryFn: () => apiGet<Explanation>(`/forecasts/${forecastId}/explanation`),
    enabled: forecastId != null,
    staleTime: STALE,
  });
}

export function useBacktest(iso3: string | null, versionId: number | null) {
  const disease = useDisease();
  return useQuery({
    queryKey: ["backtest", disease, iso3, versionId],
    queryFn: () =>
      apiGet<CountryBacktest>(forDisease(`/backtest?iso3=${iso3}&model_version_id=${versionId}`, disease)),
    enabled: !!iso3 && versionId != null,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}
