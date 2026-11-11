/**
 * Raised countries on the globe: height ∝ √(weekly average detections or reported cases)
 * on a fixed scale per measure, so heights compare over time. A country reaches
 * ELEVATION_MAX_M at ELEVATION_REF a week (a high but not record week); the rare weeks
 * above it are capped, and the legends say so. Today's largest countries stand ~250 km tall.
 */
export const ELEVATION_MAX_M = 700_000;
export const ELEVATION_REF = { positivity: 25_000, incidence: 150_000 } as const;

export function elevationNote(measure: keyof typeof ELEVATION_REF): string {
  const what = measure === "incidence" ? "reported cases" : "lab-confirmed detections";
  return `Country height ∝ √ weekly average ${what} (capped at ${ELEVATION_REF[measure].toLocaleString("en-US")} a week)`;
}
