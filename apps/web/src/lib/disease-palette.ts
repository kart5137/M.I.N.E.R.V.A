/**
 * One sequential colour ramp per disease, so each disease's globe and legend has its own
 * look: influenza amber, dengue coral-red, malaria green, cholera blue. Six steps, dark →
 * light = low → high. Every ramp passes the dataviz palette validator (--ordinal --mode dark
 * --surface #0f2f33, the globe's land colour): one hue, monotone lightness, visible step
 * gaps, darkest step ≥ 2:1 against the land.
 */
import type { DiseaseKey } from "@/lib/diseases";

export const RAMPS: Record<DiseaseKey, readonly string[]> = {
  influenza: ["#86561a", "#a46b1c", "#c48420", "#e09f30", "#f2c26a", "#fae3b2"],
  dengue: ["#a33d39", "#bd4a42", "#d65e4e", "#ea7a62", "#f6a38a", "#fcd2c3"],
  malaria: ["#3f7f3d", "#4b9547", "#5dac55", "#7cc46b", "#a6da92", "#d3efc2"],
  cholera: ["#2c68a0", "#3a82c2", "#4f9ad6", "#6cb1e5", "#97cbf0", "#cae4f8"],
};

export function rampFor(disease: DiseaseKey): readonly string[] {
  return RAMPS[disease] ?? RAMPS.influenza;
}
