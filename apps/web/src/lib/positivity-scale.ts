/**
 * Binned sequential scale for influenza test positivity (one hue, blue).
 * Validated with the dataviz palette validator against the globe surface (#0a1120):
 * monotone lightness, visible step gaps, darkest step ≥ 2:1. Dark → light = low → high.
 */
import type { CountryWindowValue } from "@/lib/types";

/** Below this many specimens in the window, positivity is shown as "too few tests". */
export const MIN_SPECIMENS = 10;

export const POSITIVITY_BINS = [
  { max: 0.05, color: "#184f95", label: "<5" },
  { max: 0.1, color: "#256abf", label: "5–10" },
  { max: 0.15, color: "#3987e5", label: "10–15" },
  { max: 0.25, color: "#6da7ec", label: "15–25" },
  { max: 0.4, color: "#9ec5f4", label: "25–40" },
  { max: Infinity, color: "#cde2fb", label: "≥40" },
] as const;

/** Reported, but too few specimens for a stable rate. */
export const FEW_SPECIMENS_COLOR = "#5b6475";
/** Detections columns: a second, distinct hue (categorical slot 2, dark-mode step). */
export const DETECTIONS_RGB: [number, number, number] = [217, 89, 38];
export const DETECTIONS_COLOR = "#d95926";

/** -1 = no data (land colour), 0 = too few specimens, 1..n = positivity bin. */
export function positivityClass(v: CountryWindowValue | undefined): number {
  if (!v || v.positivity == null) return -1;
  if ((v.specimens_tested ?? 0) < MIN_SPECIMENS) return 0;
  return POSITIVITY_BINS.findIndex((b) => v.positivity! < b.max) + 1;
}
