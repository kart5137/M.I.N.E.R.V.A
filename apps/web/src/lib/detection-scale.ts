/**
 * Colour classes for the detection layers (M6). Validated with the dataviz palette
 * validator against the globe land colour #15203a (dark mode):
 *
 * - Hot/cold (Gi*) and forecast change: diverging blue ↔ red with a neutral grey middle.
 *   Poles #3987e5 / #e66767 pass all checks; each arm (#24538f→#3987e5, #8f3d3d→#e66767)
 *   passes the ordinal checks (one hue, monotone lightness, light end ≥ 2:1).
 * - Local Moran: HH red, LL blue, outliers aqua #199e70 — all-pairs CVD 6.5 (warn band),
 *   so classes are always named in the legend and tooltip (secondary encoding).
 * - Risk: ordinal single-hue amber (#7a6a2c → #c98500 → #f2b23a), passes ordinal checks.
 * - Anomalies: neutral near-white rings; severity is the ring size, not a colour.
 *
 * Class index 0 is always "participating but not significant / neutral"; countries with
 * no class get the land colour ("no data").
 */
import type { HotspotItem, RiskLevel, Severity } from "@/lib/types";

export const NEUTRAL = "#3b4457";
export const HOT = "#e66767";
export const HOT_WEAK = "#8f3d3d";
export const COLD = "#3987e5";
export const COLD_WEAK = "#24538f";
export const OUTLIER = "#199e70";

export interface ClassScale {
  colors: string[];
  labels: string[];
}

/** Gi*: 0 ns · 1 hot (FDR) · 2 hot (p < 0.05 only) · 3 cold (p < 0.05 only) · 4 cold (FDR). */
export const GI_SCALE: ClassScale = {
  colors: [NEUTRAL, HOT, HOT_WEAK, COLD_WEAK, COLD],
  labels: [
    "Not significant",
    "Hot spot (FDR < 0.05)",
    "Hot, p < 0.05 before FDR",
    "Cold, p < 0.05 before FDR",
    "Cold spot (FDR < 0.05)",
  ],
};

export function giClass(h: HotspotItem, alpha = 0.05): number {
  const s = h.gi_star;
  if (s.p_fdr < alpha) return s.z_score > 0 ? 1 : 4;
  if (s.p_value < alpha) return s.z_score > 0 ? 2 : 3;
  return 0;
}

/** Local Moran: 0 ns · 1 HH · 2 LL · 3 outlier (HL or LH). FDR-significant only. */
export const MORAN_SCALE: ClassScale = {
  colors: [NEUTRAL, HOT, COLD, OUTLIER],
  labels: ["Not significant", "High–high cluster", "Low–low cluster", "Outlier (high–low or low–high)"],
};

export function moranClass(h: HotspotItem): number {
  switch (h.local_moran.classification) {
    case "HH":
      return 1;
    case "LL":
      return 2;
    case "HL":
    case "LH":
      return 3;
    default:
      return 0;
  }
}

export const MORAN_LABEL: Record<string, string> = {
  HH: "High–high cluster",
  LL: "Low–low cluster",
  HL: "High outlier among low neighbours",
  LH: "Low outlier among high neighbours",
  ns: "Not significant",
};

export const GI_LABEL: Record<string, string> = {
  hot: "Hot spot",
  cold: "Cold spot",
  ns: "Not significant",
};

/** Risk: 0 low · 1 moderate · 2 high. */
export const RISK_SCALE: ClassScale = {
  colors: ["#7a6a2c", "#c98500", "#f2b23a"],
  labels: ["Low", "Moderate", "High"],
};

export const RISK_INDEX: Record<RiskLevel, number> = { low: 0, moderate: 1, high: 2 };

/** Forecast change (pp): 0 within ±1 · 1 +1..5 · 2 ≥ +5 · 3 −1..−5 · 4 ≤ −5. */
export const CHANGE_SCALE: ClassScale = {
  colors: [NEUTRAL, HOT_WEAK, HOT, COLD_WEAK, COLD],
  labels: ["Within ±1 pp", "+1 to +5 pp", "≥ +5 pp", "−1 to −5 pp", "≤ −5 pp"],
};

/** Legend order for the diverging change scale (low → high). */
export const CHANGE_LEGEND_ORDER = [4, 3, 0, 1, 2];
export const GI_LEGEND_ORDER = [1, 2, 0, 3, 4];

export function changeClass(pp: number): number {
  if (pp >= 5) return 2;
  if (pp >= 1) return 1;
  if (pp <= -5) return 4;
  if (pp <= -1) return 3;
  return 0;
}

export const ANOMALY_RING = "#f1f5f9";
/** Ring radius (m) by severity, so severity is never colour-only. */
export const SEVERITY_RADIUS: Record<Severity, number> = {
  moderate: 160_000,
  high: 240_000,
  severe: 330_000,
};
export const SEVERITY_LABEL: Record<Severity, string> = {
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
};
