"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";
import { DEFAULT_DISEASE, type DiseaseKey } from "@/lib/diseases";
import { useDisease } from "@/lib/filters";
import type {
  Anomalies,
  CountryDetection,
  DetectionHistory,
  GlobalForecasts,
  Hotspots,
  RiskList,
} from "@/lib/types";

const STALE = 5 * 60_000;

function qs(params: Record<string, string | number | null | undefined>, disease?: DiseaseKey): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== "") q.set(k, String(v));
  if (disease && disease !== DEFAULT_DISEASE) q.set("disease", disease);
  return q.toString();
}

export function useAnomalies(p: { to: string | null; weeks: number; region: string | null; iso3?: string | null }, enabled = true) {
  const disease = useDisease();
  return useQuery({
    queryKey: [disease, "anomalies", p],
    queryFn: () => apiGet<Anomalies>(`/anomalies?${qs({ to: p.to, weeks: p.weeks, region: p.region, iso3: p.iso3 }, disease)}`),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useHotspots(p: { to: string | null; region: string | null }, enabled = true) {
  const disease = useDisease();
  return useQuery({
    queryKey: [disease, "hotspots", p],
    queryFn: () => apiGet<Hotspots>(`/hotspots?${qs({ to: p.to, region: p.region }, disease)}`),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useDetectionHistory(region: string | null) {
  const disease = useDisease();
  return useQuery({
    queryKey: [disease, "detection-history", region],
    queryFn: () => apiGet<DetectionHistory>(`/detection/history?${qs({ region }, disease)}`),
    staleTime: STALE,
  });
}

export function useRisk(region: string | null, enabled = true) {
  const disease = useDisease();
  return useQuery({
    queryKey: [disease, "risk", region],
    queryFn: () => apiGet<RiskList>(`/risk?${qs({ region }, disease)}`),
    enabled,
    staleTime: STALE,
  });
}

export function useGlobalForecasts(horizon: number, region: string | null, enabled = true) {
  const disease = useDisease();
  return useQuery({
    queryKey: [disease, "forecasts-global", horizon, region],
    queryFn: () => apiGet<GlobalForecasts>(`/forecasts/global?${qs({ horizon, region }, disease)}`),
    enabled,
    staleTime: STALE,
  });
}

export function useCountryDetection(iso3: string | null) {
  const disease = useDisease();
  return useQuery({
    queryKey: [disease, "country", iso3, "detection"],
    queryFn: () => apiGet<CountryDetection>(`/countries/${iso3}/detection?${qs({}, disease)}`),
    enabled: !!iso3,
    staleTime: STALE,
  });
}
