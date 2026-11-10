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
  /** Case-based diseases (dengue). `grain` says whether the value comes from weekly
   *  reports in the window or from the calendar months overlapping it. */
  cases?: number | null;
  /** Cases per 100,000 population per week. */
  incidence?: number | null;
  population?: number | null;
  grain?: "week" | "month" | null;
  periods_reported?: number | null;
  period_start?: string | null;
  period_end?: string | null;
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
  denominator?: number | null;
  note?: string | null;
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
  cases?: number | null;
  incidence?: number | null;
}

/** Influenza: positivity change (pp). Case-based: relative incidence change (%). */
export interface Mover {
  iso3: string;
  name: string;
  positivity: number | null;
  previous_positivity: number | null;
  change_pp: number | null;
  specimens_tested: number | null;
  incidence?: number | null;
  previous_incidence?: number | null;
  change_pct?: number | null;
  cases?: number | null;
}

export interface Overview {
  meta: ResponseMeta;
  window: WindowInfo;
  previous_window: WindowInfo;
  region: string | null;
  kpis: {
    /** Influenza only. */
    detections: Kpi | null;
    positivity: Kpi | null;
    countries_reporting: Kpi;
    /** Case-based diseases only. */
    cases?: Kpi | null;
    incidence?: Kpi | null;
    anomalies: Kpi | null;
    hotspots: Kpi | null;
    above_threshold: Kpi | null;
    pending: PendingKpi[];
  };
  trend: TrendPoint[];
  top_movers: Mover[];
  movers_min_specimens: number;
  movers_min_cases?: number | null;
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
    /** Unit of completeness and longest_gap. */
    grain?: "week" | "month";
  } | null;
  surveillance: {
    first_week: string | null;
    last_reported_week: string | null;
    weeks_reported: number;
    first_month?: string | null;
    last_reported_month?: string | null;
    months_reported?: number;
  };
  flu_season: SeasonType | null;
  health: HealthValue[];
  recent_window: WindowInfo;
  recent: CountryWindowValue | null;
}

export type SeasonType = "NH" | "SH" | "YR";

export interface HealthValue {
  code: string;
  label: string;
  unit: string;
  group: "health_system" | "population";
  value: number | null;
  year: number | null;
  source: string | null;
}

export interface CountryListItem {
  iso3: string;
  name: string;
  who_region: string | null;
  flu_season: SeasonType | null;
  has_geometry: boolean;
  tier: string | null;
  last_reported_week: string | null;
  weeks_reported: number;
  positivity: number | null;
  positives: number | null;
  specimens_tested: number | null;
  cases?: number | null;
  incidence?: number | null;
  grain?: "week" | "month" | null;
  last_reported_month?: string | null;
}

export type CountrySort =
  | "name"
  | "tier"
  | "positivity"
  | "specimens_tested"
  | "positives"
  | "last_reported_week"
  | "cases"
  | "incidence";

export interface CountryList {
  meta: ResponseMeta;
  window: WindowInfo;
  sort: CountrySort;
  order: "asc" | "desc";
  total: number;
  page: number;
  page_size: number;
  items: CountryListItem[];
}

export interface SeasonPoint {
  index: number;
  week_start: string;
  iso_week: number;
  reported: boolean;
  specimens_tested: number | null;
  positives: number | null;
  positivity: number | null;
  is_provisional: boolean;
}

export interface Season {
  label: string;
  start: string;
  end: string;
  is_current: boolean;
  covid_disrupted: boolean;
  weeks_reported: number;
  positives: number | null;
  specimens_tested: number | null;
  peak_positivity: number | null;
  peak_week: string | null;
  /** MEM levels for this season (M6); null when not computed. */
  thresholds: ThresholdLevels | null;
  points: SeasonPoint[];
}

export interface CountrySeasons {
  meta: ResponseMeta;
  iso3: string;
  season_type: SeasonType | null;
  season_rule: string;
  min_specimens_for_peak: number;
  seasons: Season[];
}

export type Granularity = "week" | "month" | "year";

export interface TrendBucket {
  period_start: string;
  label: string;
  weeks: number;
  countries_reporting: number;
  specimens_tested: number | null;
  positives: number | null;
  positivity: number | null;
  share_a: number | null;
  inf_a: number | null;
  inf_b: number | null;
  positivity_change_pp: number | null;
  positives_change_pct: number | null;
  partial: boolean;
}

export interface TrendSeries {
  key: string;
  label: string;
  kind: "country" | "region" | "world";
  buckets: TrendBucket[];
}

export interface Trends {
  meta: ResponseMeta;
  granularity: Granularity;
  start: string;
  end: string;
  series: TrendSeries[];
}

export interface HeatmapCell {
  iso_year: number;
  iso_week: number;
  positivity: number | null;
  specimens_tested: number | null;
  is_provisional: boolean;
}

export interface Heatmap {
  meta: ResponseMeta;
  key: string;
  label: string;
  years: number[];
  min_specimens: number;
  cells: HeatmapCell[];
}

export interface SeriesPoint {
  week_start: string;
  reported: boolean;
  specimens_tested: number | null;
  positives: number | null;
  positivity: number | null;
  is_provisional: boolean;
  cases?: number | null;
  incidence?: number | null;
}

export interface MonthPoint {
  month_start: string;
  cases: number | null;
  /** Cases per 100,000 per week (month total / weeks in the month). */
  incidence: number | null;
  is_provisional: boolean;
}

export interface CountryTimeseries {
  meta: ResponseMeta;
  iso3: string;
  window: WindowInfo;
  points: SeriesPoint[];
  monthly?: MonthPoint[];
}

/* ---------- Weather (D3) ---------- */

export interface WeatherWeek {
  week_start: string;
  /** °C, mean of daily means. */
  temperature: number;
  /** mm, weekly total. */
  precipitation: number;
  /** %, mean of daily means. */
  humidity: number;
  temperature_normal: number | null;
  precipitation_normal: number | null;
  humidity_normal: number | null;
}

export interface CountryWeather {
  iso3: string;
  point: { lat: number; lon: number; basis: "label_point" | "main_town"; elevation_m: number | null } | null;
  source: SourceRef | null;
  baseline_years: [number, number];
  first_week: string | null;
  latest_week: string | null;
  /** History is still being loaded (free API, daily quota). */
  loading: boolean;
  weeks: WeatherWeek[];
}

/* ---------- Forecasting (M5) ---------- */

export interface Metrics {
  mae: number | null;
  rmse: number | null;
  mase: number | null;
  skill_vs_snaive: number | null;
  coverage_80: number | null;
  coverage_95: number | null;
  n_obs: number | null;
  n_origins: number | null;
}

export interface ModelSummary {
  id: number;
  model_type: string;
  label: string;
  kind: "baseline" | "ml";
  horizon_weeks: number;
  is_active: boolean;
  selection_note: string | null;
  metrics: Metrics;
}

export interface ModelRun {
  meta: ResponseMeta;
  run_key: string | null;
  target: string;
  trained_at: string | null;
  train_end: string | null;
  eval_start: string | null;
  eval_end: string | null;
  models: ModelSummary[];
}

export interface ModelDetail {
  meta: ResponseMeta;
  id: number;
  run_key: string;
  model_type: string;
  label: string;
  kind: "baseline" | "ml";
  target: string;
  horizon_weeks: number;
  is_active: boolean;
  selection_note: string | null;
  train_start: string | null;
  train_end: string;
  trained_at: string;
  features: string[] | null;
  hyperparams: Record<string, unknown> | null;
  git_sha: string | null;
  artefact_uri: string | null;
  metrics: Metrics;
  reference: Metrics;
  importance: { feature: string; label: string; value: number }[];
  error_by_origin: { origin_week: string; mae: number; n: number }[];
  countries: { iso3: string; name: string; metrics: Metrics }[];
}

export interface ForecastOut {
  id: number;
  model_version_id: number;
  model_type: string;
  label: string;
  is_active: boolean;
  horizon_weeks: number;
  origin_week: string;
  target_week: string;
  point: number;
  lo80: number | null;
  hi80: number | null;
  lo95: number | null;
  hi95: number | null;
  has_explanation: boolean;
}

export interface CountryForecasts {
  meta: ResponseMeta;
  iso3: string;
  run_key: string | null;
  eligible: boolean;
  reason: string | null;
  forecasts: ForecastOut[];
  country_metrics: Record<string, Metrics>;
}

export interface Explanation {
  forecast_id: number;
  model_type: string;
  horizon_weeks: number;
  /** "positivity" (logit scale) or "incidence" (log of incidence + one case per 100,000). */
  target: "positivity" | "incidence";
  base_value: number | null;
  /** The forecast on the model scale. */
  prediction_logit: number;
  point: number;
  other_features: number;
  contributions: {
    feature: string;
    label: string;
    shap_value: number;
    feature_value: number | null;
    /** Dengue level features as incidence per 100,000. */
    natural_value?: number | null;
    rank: number;
  }[];
}

export interface CountryBacktest {
  meta: ResponseMeta;
  iso3: string;
  model_version_id: number;
  model_type: string;
  horizon_weeks: number;
  points: {
    origin_week: string;
    target_week: string;
    point: number;
    lo80: number | null;
    hi80: number | null;
    lo95: number | null;
    hi95: number | null;
    actual: number;
  }[];
}

/* ---------- Detection (M6) ---------- */

export interface DetectionRunInfo {
  run_key: string;
  reference_week: string;
  finished_at: string | null;
}

export type Severity = "moderate" | "high" | "severe";

export interface AnomalyItem {
  iso3: string;
  name: string;
  who_region: string | null;
  week_start: string;
  method: "seasonal_ewma" | "isolation_forest";
  observed: number;
  expected: number | null;
  upper_band: number | null;
  score: number;
  ewma: number | null;
  ewma_limit: number | null;
  specimens_tested: number | null;
  severity: Severity | null;
  is_provisional: boolean;
}

export interface AnomalyCountry {
  iso3: string;
  weeks_flagged: number;
  latest_week: string;
  max_severity: Severity;
  max_score: number;
}

export interface Anomalies {
  meta: ResponseMeta;
  run: DetectionRunInfo | null;
  window: WindowInfo;
  region: string | null;
  iso3: string | null;
  method_note: string;
  items: AnomalyItem[];
  by_country: AnomalyCountry[];
}

export interface LocalStat {
  stat_value: number;
  z_score: number;
  p_value: number;
  p_fdr: number;
  classification: string;
}

export interface HotspotItem {
  iso3: string;
  name: string;
  who_region: string | null;
  value: number;
  n_neighbours: number;
  neighbour_source: "queen" | "knn";
  gi_star: LocalStat;
  local_moran: LocalStat;
}

export interface Hotspots {
  meta: ResponseMeta;
  run: DetectionRunInfo | null;
  window: WindowInfo | null;
  region: string | null;
  available_from: string | null;
  available_to: string | null;
  weights_spec: string | null;
  permutations: number;
  fdr_alpha: number;
  items: HotspotItem[];
}

export interface DetectionHistory {
  meta: ResponseMeta;
  region: string | null;
  points: {
    week_start: string;
    hot: number;
    cold: number;
    participants: number;
    anomalies: number;
    is_provisional: boolean;
  }[];
}

export interface ThresholdLevels {
  season: string;
  season_start: string;
  method: string;
  epidemic_threshold: number;
  post_threshold: number | null;
  medium: number;
  high: number;
  very_high: number;
  n_seasons_used: number;
  seasons_used: string[];
  quality_note: string | null;
}

export type RiskLevel = "low" | "moderate" | "high";

export interface RiskItem {
  iso3: string;
  name: string;
  who_region: string | null;
  assessed_week: string;
  target_week: string;
  risk_level: RiskLevel;
  rule: string;
  forecast_point: number;
  forecast_lo80: number | null;
  forecast_hi80: number | null;
  model_type: string;
  /** "mem" (season thresholds) or "endemic_channel" (dengue: the target week's usual range). */
  method: "mem" | "endemic_channel";
  /** MEM epidemic threshold / high intensity, or top of the channel (75th) / 90th percentile. */
  epidemic_threshold: number | null;
  high_threshold: number | null;
  season: string | null;
  /** MEM levels; null for the endemic channel. */
  thresholds: ThresholdLevels | null;
}

export interface ChannelWeek {
  iso_week: number;
  week_start: string;
  median: number;
  q75: number;
  p90: number;
}

export interface EndemicChannel {
  year: number;
  years_used: number[];
  excluded_years: number[];
  weeks: ChannelWeek[];
}

export interface RiskList {
  meta: ResponseMeta;
  run: DetectionRunInfo | null;
  region: string | null;
  rule: string;
  items: RiskItem[];
  not_assessed: { iso3: string; name: string; reason: string }[];
}

export interface HotspotStatus {
  window_end: string;
  value: number;
  gi_star: LocalStat;
  local_moran: LocalStat;
  n_neighbours: number;
  neighbour_source: "queen" | "knn";
}

export interface CountryDetection {
  meta: ResponseMeta;
  run: DetectionRunInfo | null;
  iso3: string;
  thresholds: ThresholdLevels | null;
  thresholds_reason: string | null;
  /** Dengue: the latest year's endemic channel. */
  channel?: EndemicChannel | null;
  risk: RiskItem | null;
  anomalies: AnomalyItem[];
  hotspots: HotspotStatus[];
}

export interface GlobalForecastItem {
  iso3: string;
  name: string;
  who_region: string | null;
  origin_week: string;
  target_week: string;
  origin_value: number | null;
  point: number;
  lo80: number | null;
  hi80: number | null;
  /** Influenza: point − origin, percentage points. */
  change_pp: number | null;
  /** Dengue: relative change from the origin week, percent. */
  change_pct: number | null;
}

export interface GlobalForecasts {
  meta: ResponseMeta;
  run_key: string | null;
  horizon_weeks: number;
  model_type: string | null;
  model_label: string | null;
  items: GlobalForecastItem[];
}

/* ---------- Alerts, reports, about (M7) ---------- */

export type AlertType = "new_anomaly" | "new_hotspot" | "risk_escalation" | "sustained_growth";
export type AlertSeverity = "low" | "medium" | "high";

export interface AlertItem {
  id: number;
  iso3: string;
  name: string;
  who_region: string | null;
  alert_type: AlertType;
  severity: AlertSeverity;
  week_start: string;
  title: string;
  details: Record<string, unknown>;
  status: "active" | "retracted";
  created_at: string;
  retracted_at: string | null;
}

export interface AlertList {
  meta: ResponseMeta;
  rules: Record<AlertType, string>;
  total: number;
  page: number;
  page_size: number;
  by_type: Partial<Record<AlertType, number>>;
  by_severity: Partial<Record<AlertSeverity, number>>;
  items: AlertItem[];
}

export interface ReportSummary {
  id: number;
  title: string;
  scope: "global" | "country";
  iso3: string | null;
  region: string | null;
  period_start: string;
  period_end: string;
  weeks: number;
  generator: string;
  template_version: string;
  inputs_sha256: string;
  created_at: string;
  alerts: number;
}

export interface ReportList {
  total: number;
  page: number;
  page_size: number;
  items: ReportSummary[];
}

/** Influenza weeks carry positivity, positives and specimens; dengue weeks cases and incidence. */
export interface ReportContentWeek {
  week_start: string;
  positivity?: number | null;
  positives?: number | null;
  specimens_tested?: number | null;
  cases?: number | null;
  incidence?: number | null;
  provisional: boolean;
}

export interface ReportDetail extends ReportSummary {
  content: {
    disease: { key: string; name: string };
    /** Present on dengue reports. */
    metric?: "incidence";
    monthly?: { month_start: string; cases: number | null; incidence: number | null; provisional: boolean }[];
    period: { start: string; end: string; previous_start: string; previous_end: string; weeks: number; includes_provisional: boolean };
    weekly: ReportContentWeek[];
    [key: string]: unknown;
  };
  rendered_md: string;
}

export interface GenerateReportRequest {
  scope: "global" | "country";
  iso3?: string | null;
  region?: string | null;
  to?: string | null;
  weeks: number;
}

export interface GenerateReportResponse {
  report: ReportDetail;
  reused: boolean;
}

export interface Verification {
  report_id: number;
  stored_sha256: string;
  current_sha256: string;
  inputs_identical: boolean;
  rendering_identical: boolean;
  regenerated_identical: boolean;
  changed_sections: string[];
}

export interface About {
  meta: ResponseMeta;
  sources: {
    key: string;
    name: string;
    url: string | null;
    licence: string | null;
    attribution: string | null;
    notes: string | null;
    last_ingestion: string | null;
    last_status: string | null;
    stored_rows: number;
  }[];
  coverage_reference_week: string | null;
  tiers: { tier: string; countries: number; rule: string }[];
  forecast_run: {
    run_key: string;
    trained_at: string | null;
    train_end: string | null;
    eval_start: string | null;
    eval_end: string | null;
    models: { id: number; model_type: string; label: string; horizon_weeks: number; selection_note: string | null; metrics: Metrics }[];
  } | null;
  detection_run: {
    run_key: string;
    finished_at: string | null;
    reference_week: string;
    settings: Record<string, unknown>;
    risk: Record<string, number> | null;
    alerts: { active: number; by_type: Record<string, number>; retracted_now: number } | null;
    anomalies: Record<string, number> | null;
    hotspots: { rows: number; windows: number } | null;
    thresholds_current_usable: number | null;
  } | null;
  limitations: string[];
}
