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
