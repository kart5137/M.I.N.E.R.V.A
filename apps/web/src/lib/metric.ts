/**
 * How a disease's modelled value is shown. Influenza forecasts and detection run on test
 * positivity (a fraction, shown as %); dengue (D4) on weekly incidence per 100,000.
 */

import type { DiseaseKey } from "@/lib/diseases";
import { formatPct, formatRate, formatSigned } from "@/lib/format";

export interface Metric {
  key: "positivity" | "incidence";
  /** "Positivity" / "Incidence" */
  label: string;
  /** Lower-case noun for sentences: "test positivity" / "incidence". */
  noun: string;
  /** Unit suffix for headers: "" for %, "per 100,000" for incidence. */
  unit: string;
  /** Short unit for compact labels. */
  short: string;
  format: (v: number | null | undefined) => string;
  /** Interval bounds, compact. */
  formatBound: (v: number | null | undefined) => string;
  /** Axis tick labels. */
  axis: (v: number) => string;
  /** Change from the origin week: pp for positivity, % for incidence. */
  change: (item: { change_pp?: number | null; change_pct?: number | null }) => number | null;
  formatChange: (v: number) => string;
  changeUnit: string;
}

const POSITIVITY: Metric = {
  key: "positivity",
  label: "Positivity",
  noun: "test positivity",
  unit: "",
  short: "%",
  format: (v) => formatPct(v),
  formatBound: (v) => formatPct(v, 0),
  axis: (v) => `${Math.round(v * 100)}%`,
  change: (i) => i.change_pp ?? null,
  formatChange: (v) => formatSigned(v, 1, " pp"),
  changeUnit: "pp",
};

const INCIDENCE: Metric = {
  key: "incidence",
  label: "Incidence",
  noun: "incidence",
  unit: "per 100,000",
  short: "/100k",
  format: formatRate,
  formatBound: formatRate,
  axis: (v) => formatRate(v),
  change: (i) => i.change_pct ?? null,
  formatChange: (v) => formatSigned(v, 0, "%"),
  changeUnit: "%",
};

export function metricFor(disease: DiseaseKey): Metric {
  return disease === "dengue" ? INCIDENCE : POSITIVITY;
}
