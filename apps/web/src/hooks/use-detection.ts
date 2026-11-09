"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import type {
  Anomalies,
  CountryDetection,
  DetectionHistory,
  GlobalForecasts,
  Hotspots,
  RiskList,
} from "@/lib/types";

const STALE = 5 * 60_000;

function qs(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== "") q.set(k, String(v));
  return q.toString();
}

export function useAnomalies(p: { to: string | null; weeks: number; region: string | null; iso3?: string | null }, enabled = true) {
  return useQuery({
    queryKey: ["anomalies", p],
    queryFn: () => apiGet<Anomalies>(`/anomalies?${qs({ to: p.to, weeks: p.weeks, region: p.region, iso3: p.iso3 })}`),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useHotspots(p: { to: string | null; region: string | null }, enabled = true) {
  return useQuery({
    queryKey: ["hotspots", p],
    queryFn: () => apiGet<Hotspots>(`/hotspots?${qs({ to: p.to, region: p.region })}`),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useDetectionHistory(region: string | null) {
  return useQuery({
    queryKey: ["detection-history", region],
    queryFn: () => apiGet<DetectionHistory>(`/detection/history?${qs({ region })}`),
    staleTime: STALE,
  });
}

export function useRisk(region: string | null, enabled = true) {
  return useQuery({
    queryKey: ["risk", region],
    queryFn: () => apiGet<RiskList>(`/risk?${qs({ region })}`),
    enabled,
    staleTime: STALE,
  });
}

export function useGlobalForecasts(horizon: number, region: string | null, enabled = true) {
  return useQuery({
    queryKey: ["forecasts-global", horizon, region],
    queryFn: () => apiGet<GlobalForecasts>(`/forecasts/global?${qs({ horizon, region })}`),
    enabled,
    staleTime: STALE,
  });
}

export function useCountryDetection(iso3: string | null) {
  return useQuery({
    queryKey: ["country", iso3, "detection"],
    queryFn: () => apiGet<CountryDetection>(`/countries/${iso3}/detection`),
    enabled: !!iso3,
    staleTime: STALE,
  });
}
