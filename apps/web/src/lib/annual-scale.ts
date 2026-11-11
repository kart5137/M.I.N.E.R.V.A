/**
 * Yearly malaria (C1): binned scale for estimated cases per 1,000 population at risk, and
 * formatting for estimates with uncertainty ranges. Same validated amber steps as the
 * other choropleths (lib/positivity-scale.ts). Breaks are roughly logarithmic: most
 * endemic countries outside Africa are under 10, high-burden African countries 100–500
 * (WHO World Malaria Report estimates, 2024). A real zero (no indigenous cases) has its
 * own neutral class, distinct from "no estimate".
 */
import { formatCompact, formatInt } from "@/lib/format";
import { FEW_SPECIMENS_COLOR, POSITIVITY_BINS } from "@/lib/positivity-scale";
import type { AnnualValues, MeasureValue } from "@/lib/types";

const BREAKS = [
  { max: 1, label: "<1" },
  { max: 10, label: "1–10" },
  { max: 50, label: "10–50" },
  { max: 100, label: "50–100" },
  { max: 250, label: "100–250" },
  { max: Infinity, label: "≥250" },
] as const;

export const ZERO_COLOR = FEW_SPECIMENS_COLOR;
export const MALARIA_BINS = BREAKS.map((b, i) => ({ ...b, color: POSITIVITY_BINS[i].color }));
/** Fill colours by class: 0 = zero cases, 1..6 = bins. */
export const MALARIA_FILL_COLORS = [ZERO_COLOR, ...MALARIA_BINS.map((b) => b.color)];

/** -1 = no estimate (land colour), 0 = zero, 1..6 = bin of estimated incidence. */
export function malariaClass(values: AnnualValues | undefined): number {
  const v = values?.est_incidence?.value;
  if (v == null) return -1;
  if (v === 0) return 0;
  return MALARIA_BINS.findIndex((b) => v < b.max) + 1;
}

/** Large counts compact (281.7M); small ones in full. */
export function formatCount(v: number | null | undefined): string {
  if (v == null) return "—";
  return Math.abs(v) >= 100_000 ? formatCompact(v) : formatInt(v);
}

/** Rates: 2 decimals under 1, 1 under 100, none above. */
export function formatAnnualRate(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v === 0) return "0";
  if (v < 1) return v.toFixed(2);
  if (v < 100) return v.toFixed(1);
  return Math.round(v).toLocaleString("en-US");
}

/** "1,200 (900–1,500)" — the range only when WHO gives one. */
export function withRange(m: MeasureValue | undefined, fmt: (v: number) => string): string {
  if (!m) return "—";
  return m.low != null && m.high != null ? `${fmt(m.value)} (${fmt(m.low)}–${fmt(m.high)})` : fmt(m.value);
}

/** Relative change from the previous year, or null when either year is missing or zero. */
export function yearChange(cur: MeasureValue | undefined, prev: MeasureValue | undefined): number | null {
  if (!cur || !prev || prev.value === 0) return null;
  return ((cur.value - prev.value) / prev.value) * 100;
}
