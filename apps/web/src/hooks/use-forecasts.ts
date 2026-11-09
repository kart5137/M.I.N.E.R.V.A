"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import type { CountryBacktest, CountryForecasts, Explanation, ModelDetail, ModelRun } from "@/lib/types";

const STALE = 5 * 60_000;

export function useModelRun() {
  return useQuery({ queryKey: ["models"], queryFn: () => apiGet<ModelRun>("/models"), staleTime: STALE });
}

export function useModelDetail(id: number | null) {
  return useQuery({
    queryKey: ["models", id],
    queryFn: () => apiGet<ModelDetail>(`/models/${id}`),
    enabled: id != null,
    staleTime: STALE,
  });
}

export function useCountryForecasts(iso3: string | null) {
  return useQuery({
    queryKey: ["forecasts", iso3],
    queryFn: () => apiGet<CountryForecasts>(`/forecasts?iso3=${iso3}`),
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
  return useQuery({
    queryKey: ["backtest", iso3, versionId],
    queryFn: () => apiGet<CountryBacktest>(`/backtest?iso3=${iso3}&model_version_id=${versionId}`),
    enabled: !!iso3 && versionId != null,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}
