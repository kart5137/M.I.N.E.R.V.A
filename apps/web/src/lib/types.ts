/** Response types mirroring services/api/app/schemas. Keep in sync. */

export interface DiseaseStatus {
  key: string;
  name: string;
  reference_week: string | null;
  provisional_from: string | null;
  latest_week: string | null;
  country_weeks: number;
}

export interface IngestionSummary {
  source: string;
  status: string;
  finished_at: string | null;
  loaded_rows: number | null;
}

export interface MetaStatus {
  database: string;
  postgis_version: string | null;
  schema_revision: string | null;
  diseases: DiseaseStatus[];
  last_ingestions: IngestionSummary[];
  demo: boolean;
}

export interface SourceRef {
  key: string;
  name: string;
  attribution: string | null;
}

/** Data-availability context returned with every surveillance response. */
export interface ResponseMeta {
  disease: string;
  first_week: string;
  reference_week: string;
  provisional_from: string | null;
  latest_week: string;
  sources: SourceRef[];
  demo: boolean;
}

export interface WindowInfo {
  start: string;
  end: string;
  weeks: number;
  includes_provisional: boolean;
}

export interface CountryWindowValue {
  iso3: string;
  name: string;
  who_region: string | null;
  has_geometry: boolean;
  specimens_tested: number | null;
  positives: number | null;
  positivity: number | null;
  weeks_reported: number;
  provisional_weeks: number;
  tier: string | null;
}

export interface GlobalSurveillance {
  meta: ResponseMeta;
  window: WindowInfo;
  region: string | null;
  countries: CountryWindowValue[];
}

export interface Kpi {
  value: number | null;
  previous: number | null;
  change: number | null;
  change_unit: "percent" | "pp" | "count";
}

export interface PendingKpi {
  key: string;
  label: string;
  available_in: string;
}

export interface TrendPoint {
  week_start: string;
  specimens_tested: number | null;
  positives: number | null;
  positivity: number | null;
  countries_reporting: number;
  is_provisional: boolean;
}

export interface Mover {
  iso3: string;
  name: string;
  positivity: number;
  previous_positivity: number;
  change_pp: number;
  specimens_tested: number;
}

export interface Overview {
  meta: ResponseMeta;
  window: WindowInfo;
  previous_window: WindowInfo;
  region: string | null;
  kpis: {
    detections: Kpi;
    positivity: Kpi;
    countries_reporting: Kpi;
    pending: PendingKpi[];
  };
  trend: TrendPoint[];
  top_movers: Mover[];
  movers_min_specimens: number;
}

export interface CountryProfile {
  meta: ResponseMeta;
  iso3: string;
  iso2: string | null;
  name: string;
  who_region: string | null;
  hemisphere: string | null;
  transmission_zone: string | null;
  has_geometry: boolean;
  population: { year: number; value: number; source: string } | null;
  coverage: {
    reference_week: string;
    tier: string;
    completeness: number;
    longest_gap: number;
    median_tests: number | null;
    weeks_since_last: number | null;
  } | null;
  surveillance: {
    first_week: string | null;
    last_reported_week: string | null;
    weeks_reported: number;
  };
}

export interface SeriesPoint {
  week_start: string;
  reported: boolean;
  specimens_tested: number | null;
  positives: number | null;
  positivity: number | null;
  is_provisional: boolean;
}

export interface CountryTimeseries {
  meta: ResponseMeta;
  iso3: string;
  window: WindowInfo;
  points: SeriesPoint[];
}
