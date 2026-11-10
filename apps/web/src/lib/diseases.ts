/**
 * Diseases the dashboard can show, and which features each one has. Influenza has the
 * full platform. Dengue (post-MVP phase P1) has surveillance, weather, forecasting,
 * detection, alerts and reports (D4); Analytics compares influenza test positivity with
 * health-system indicators and stays influenza-only.
 */

export type DiseaseKey = "influenza" | "dengue";

export type Feature = "forecasting" | "detection" | "analytics" | "reports";

export interface DiseaseInfo {
  key: DiseaseKey;
  label: string;
  /** Reported case counts (dengue) rather than laboratory test results (influenza). */
  caseBased: boolean;
  features: Record<Feature, boolean>;
  /** Why a feature is not available, shown instead of the page. */
  unavailable?: Partial<Record<Feature, string>>;
  /** Short attribution shown in page footers. */
  sourceNote: string;
}

export const DISEASES: Record<DiseaseKey, DiseaseInfo> = {
  influenza: {
    key: "influenza",
    label: "Influenza",
    caseBased: false,
    features: { forecasting: true, detection: true, analytics: true, reports: true },
    sourceNote: "WHO FluNet (GISRS)",
  },
  dengue: {
    key: "dengue",
    label: "Dengue",
    caseBased: true,
    features: { forecasting: true, detection: true, analytics: false, reports: true },
    unavailable: {
      analytics:
        "Analytics compares influenza test positivity with health-system indicators and subtype mixes; dengue has " +
        "reported cases instead, so this page covers influenza only. Dengue trends, forecasts and outbreak " +
        "detection are on the other pages.",
    },
    sourceNote: "WHO Global Dengue Surveillance",
  },
};

export const DISEASE_KEYS = Object.keys(DISEASES) as DiseaseKey[];
export const DEFAULT_DISEASE: DiseaseKey = "influenza";

export const FEATURE_LABELS: Record<Feature, string> = {
  forecasting: "Forecasting",
  detection: "Outbreak detection",
  analytics: "Analytics",
  reports: "Alerts and intelligence reports",
};

export function isDiseaseKey(v: string | null | undefined): v is DiseaseKey {
  return v != null && v in DISEASES;
}
