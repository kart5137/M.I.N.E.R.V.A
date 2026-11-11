/**
 * Binned scale for weekly COUNTS (average reported cases or lab detections a week in the
 * window), the "Total cases" country fill. Counts are heavy-tailed (most countries report
 * tens a week, a few report tens of thousands), so the breaks are roughly logarithmic.
 * Six bins, to match the six-step disease ramps. Unlike per-100,000 rates, counts grow with
 * population: a large country can top this scale with a modest rate.
 */
import type { CountryWindowValue } from "@/lib/types";

import { weeklyCases } from "./incidence-scale";

export type CountMeasure = "cases" | "detections";

const BREAKS: Record<CountMeasure, { max: number; label: string }[]> = {
  cases: [
    { max: 10, label: "<10" },
    { max: 100, label: "10–100" },
    { max: 1_000, label: "100–1K" },
    { max: 5_000, label: "1K–5K" },
    { max: 20_000, label: "5K–20K" },
    { max: Infinity, label: "≥20K" },
  ],
  detections: [
    { max: 10, label: "<10" },
    { max: 50, label: "10–50" },
    { max: 200, label: "50–200" },
    { max: 500, label: "200–500" },
    { max: 2_000, label: "500–2K" },
    { max: Infinity, label: "≥2K" },
  ],
};

export function countBins(measure: CountMeasure) {
  return BREAKS[measure];
}

/** Average reported cases (or lab detections) a week over the window; null = no report. */
export function weeklyCount(v: CountryWindowValue | undefined, measure: CountMeasure, windowWeeks: number): number | null {
  if (!v) return null;
  if (measure === "cases") return weeklyCases(v);
  return v.positives == null ? null : v.positives / Math.max(1, windowWeeks);
}

/** -1 = no report (land colour), 1..6 = bin (0 is reserved for "no rate" on rate scales). */
export function countClass(weekly: number | null, measure: CountMeasure): number {
  if (weekly == null) return -1;
  return BREAKS[measure].findIndex((b) => weekly < b.max) + 1;
}
