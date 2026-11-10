/**
 * Binned sequential scale for influenza test positivity (one hue, amber).
 * Validated with the dataviz palette validator (--ordinal) against the globe land colour
 * #0f2f33: monotone lightness, visible step gaps, darkest step 2.28:1, hue spread 18°.
 * Dark → light = low → high.
 */
import type { CountryWindowValue } from "@/lib/types";

/** Below this many specimens in the window, positivity is shown as "too few tests". */
export const MIN_SPECIMENS = 10;

export const POSITIVITY_BINS = [
  { max: 0.05, color: "#86561a", label: "<5" },
  { max: 0.1, color: "#a46b1c", label: "5–10" },
  { max: 0.15, color: "#c48420", label: "10–15" },
  { max: 0.25, color: "#e09f30", label: "15–25" },
  { max: 0.4, color: "#f2c26a", label: "25–40" },
  { max: Infinity, color: "#fae3b2", label: "≥40" },
] as const;

/** Reported, but too few specimens for a stable rate. */
export const FEW_SPECIMENS_COLOR = "#4d6662";
/** Detections columns: teal, a hue the amber fill never uses (categorical slot 1, lifted for 3D). */
export const DETECTIONS_RGB: [number, number, number] = [79, 207, 189];
export const DETECTIONS_COLOR = "#4fcfbd";

/** -1 = no data (land colour), 0 = too few specimens, 1..n = positivity bin. */
export function positivityClass(v: CountryWindowValue | undefined): number {
  if (!v || v.positivity == null) return -1;
  if ((v.specimens_tested ?? 0) < MIN_SPECIMENS) return 0;
  return POSITIVITY_BINS.findIndex((b) => v.positivity! < b.max) + 1;
}
