/**
 * Diseases the dashboard can show, and which features each one has. Influenza has the
 * full platform. Dengue (post-MVP phase P1) has surveillance, weather, forecasting,
 * detection, alerts and reports (D4); Analytics compares influenza test positivity with
 * health-system indicators and stays influenza-only. Malaria (C1) is yearly: World Malaria
 * Report estimates and reported cases on the Overview, Countries and country pages only.
 */

export type DiseaseKey = "influenza" | "dengue" | "malaria";

export type Feature = "surveillance" | "forecasting" | "detection" | "analytics" | "reports";

export interface DiseaseInfo {
  key: DiseaseKey;
  label: string;
  /** Reported case counts (dengue) rather than laboratory test results (influenza). */
  caseBased: boolean;
  /** Reporting grain: weekly series (influenza, dengue) or yearly totals (malaria). */
  grain: "week" | "year";
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
    grain: "week",
    features: { surveillance: true, forecasting: true, detection: true, analytics: true, reports: true },
    sourceNote: "WHO FluNet (GISRS)",
  },
  dengue: {
    key: "dengue",
    label: "Dengue",
    caseBased: true,
    grain: "week",
    features: { surveillance: true, forecasting: true, detection: true, analytics: false, reports: true },
    unavailable: {
      analytics:
        "Analytics compares influenza test positivity with health-system indicators and subtype mixes; dengue has " +
        "reported cases instead, so this page covers influenza only. Dengue trends, forecasts and outbreak " +
        "detection are on the other pages.",
    },
    sourceNote: "WHO Global Dengue Surveillance",
  },
  malaria: {
    key: "malaria",
    label: "Malaria",
    caseBased: true,
    grain: "year",
    features: { surveillance: false, forecasting: false, detection: false, analytics: false, reports: false },
    unavailable: {
      surveillance:
        "Malaria data are yearly country totals (WHO World Malaria Report), so there is no weekly globe or time " +
        "slider. The yearly world map is on the Overview, with a year selector.",
      forecasting:
        "Malaria data are yearly totals. One value a year is too little to forecast weeks ahead honestly, so " +
        "there are no malaria forecasts. Trends by year are on the Overview and country pages.",
      detection:
        "Anomaly and hot-spot detection run on weekly series; malaria data are yearly totals, so they do not apply.",
      analytics:
        "Analytics compares influenza test positivity with health-system indicators; it covers influenza only.",
      reports:
        "Alerts and reports are built on weekly detection, which yearly malaria data do not support.",
    },
    sourceNote: "WHO Global Health Observatory (World Malaria Report)",
  },
};

export const DISEASE_KEYS = Object.keys(DISEASES) as DiseaseKey[];
export const DEFAULT_DISEASE: DiseaseKey = "influenza";

export const FEATURE_LABELS: Record<Feature, string> = {
  surveillance: "Weekly global surveillance",
  forecasting: "Forecasting",
  detection: "Outbreak detection",
  analytics: "Analytics",
  reports: "Alerts and intelligence reports",
};

export function isDiseaseKey(v: string | null | undefined): v is DiseaseKey {
  return v != null && v in DISEASES;
}
