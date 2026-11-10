/**
 * Diseases the dashboard can show, and which features each one has. Influenza has the
 * full platform; dengue (post-MVP phase P1) has surveillance views now, with forecasting,
 * detection, analytics and reports arriving in phase D4.
 */

export type DiseaseKey = "influenza" | "dengue";

export type Feature = "forecasting" | "detection" | "analytics" | "reports";

export interface DiseaseInfo {
  key: DiseaseKey;
  label: string;
  /** Reported case counts (dengue) rather than laboratory test results (influenza). */
  caseBased: boolean;
  features: Record<Feature, boolean>;
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
    features: { forecasting: false, detection: false, analytics: false, reports: false },
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
