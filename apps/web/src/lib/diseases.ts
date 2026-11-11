/**
 * Diseases the dashboard can show, and which features each one has. Influenza has the
 * full platform. Dengue (post-MVP phase P1) has surveillance, weather, forecasting,
 * detection, alerts and reports (D4); Analytics compares influenza test positivity with
 * health-system indicators and stays influenza-only. Malaria (C1) is yearly: World Malaria
 * Report estimates and reported cases on the Overview, Countries and country pages only.
 * Cholera (C2) has weekly outbreak reports since 2023 (maps, trends, deaths) and yearly
 * history to 2016, without forecasting, detection or alerts. COVID-19 (C3) has weekly
 * cases and deaths since 2020 and yearly totals summed from them, likewise without models.
 */

export type DiseaseKey = "influenza" | "dengue" | "malaria" | "cholera" | "covid19";

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
  /** Case fatality (deaths ÷ reported cases) is meaningful and shown (cholera). */
  caseFatality?: boolean;
  /** Country pages show reported cases and deaths by year (weekly sums, history). */
  yearlyHistory?: boolean;
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
  cholera: {
    key: "cholera",
    label: "Cholera",
    caseBased: true,
    grain: "week",
    features: { surveillance: true, forecasting: false, detection: false, analytics: false, reports: false },
    unavailable: {
      forecasting:
        "Cholera reports cover outbreaks since January 2023 only, and countries report while an outbreak lasts. " +
        "That is too short and patchy for honest forecasts. Weekly trends and yearly history are on the Overview, " +
        "Global Surveillance and country pages.",
      detection:
        "Anomaly and hot-spot detection need several years of regular weekly reporting; cholera reporting covers " +
        "outbreaks since 2023 only.",
      analytics:
        "Analytics compares influenza test positivity with health-system indicators; it covers influenza only.",
      reports:
        "Alerts and reports are built on outbreak detection, which cholera's short outbreak-only reporting does " +
        "not support yet.",
    },
    sourceNote: "WHO Global Cholera and AWD Dashboard",
    caseFatality: true,
    yearlyHistory: true,
  },
  covid19: {
    key: "covid19",
    label: "COVID-19",
    caseBased: true,
    grain: "week",
    features: { surveillance: true, forecasting: false, detection: false, analytics: false, reports: false },
    unavailable: {
      forecasting:
        "Since 2023 most countries test and report COVID-19 far less, and many stopped weekly reporting, so " +
        "reported cases no longer track infections steadily enough for honest forecasts. Weekly trends and yearly " +
        "totals are on the Overview, Global Surveillance and country pages.",
      detection:
        "Anomaly and hot-spot detection compare a week with the same weeks of earlier years. COVID-19 reporting " +
        "changed too much between the pandemic years and now for that comparison to mean anything.",
      analytics:
        "Analytics compares influenza test positivity with health-system indicators; it covers influenza only.",
      reports:
        "Alerts and reports are built on outbreak detection, which COVID-19's changing reporting does not support.",
    },
    sourceNote: "WHO COVID-19 dashboard",
    yearlyHistory: true,
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

/** The disease name inside a sentence: "dengue", but "COVID-19" stays as written. */
export function diseaseNoun(info: DiseaseInfo): string {
  return /[A-Z]{2}/.test(info.label) ? info.label : info.label.toLowerCase();
}

export function isDiseaseKey(v: string | null | undefined): v is DiseaseKey {
  return v != null && v in DISEASES;
}
