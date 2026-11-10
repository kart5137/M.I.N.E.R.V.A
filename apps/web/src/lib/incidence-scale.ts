/**
 * Binned sequential scale for reported dengue incidence (cases per 100,000 per week).
 * Same validated amber steps as the positivity scale (lib/positivity-scale.ts); only the
 * breaks differ. Breaks are roughly logarithmic because incidence is heavy-tailed: in a
 * 4-week window most countries report under 1 per 100,000 per week, outbreaks reach
 * 20–300 (WHO data, 2024–2026).
 */
import { POSITIVITY_BINS } from "@/lib/positivity-scale";
import type { CountryWindowValue } from "@/lib/types";

const BREAKS = [
  { max: 0.1, label: "<0.1" },
  { max: 1, label: "0.1–1" },
  { max: 5, label: "1–5" },
  { max: 20, label: "5–20" },
  { max: 50, label: "20–50" },
  { max: Infinity, label: "≥50" },
] as const;

export const INCIDENCE_BINS = BREAKS.map((b, i) => ({ ...b, color: POSITIVITY_BINS[i].color }));

/** -1 = no report (land colour), 0 = reported but no population (no rate), 1..n = bin. */
export function incidenceClass(v: CountryWindowValue | undefined): number {
  if (!v || v.cases == null) return -1;
  if (v.incidence == null) return 0;
  return INCIDENCE_BINS.findIndex((b) => v.incidence! < b.max) + 1;
}

/** Average reported cases per week over the reported periods (column height). */
export function weeklyCases(v: CountryWindowValue): number | null {
  if (v.cases == null || !v.period_start || !v.period_end) return null;
  const days = (Date.parse(v.period_end) - Date.parse(v.period_start)) / 86_400_000 + 1;
  if (v.grain === "week") return v.cases / Math.max(1, v.periods_reported ?? 1);
  return days > 0 ? (v.cases * 7) / days : null;
}

/** "Jul–Aug 2026" for the months a monthly value covers. */
export function monthSpan(start: string, end: string): string {
  const fmt = (d: string, year: boolean) =>
    new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", {
      month: "short",
      ...(year ? { year: "numeric" } : {}),
      timeZone: "UTC",
    });
  const a = fmt(start, false);
  const b = fmt(end, true);
  return a === b.split(" ")[0] ? b : `${a}–${b}`;
}
