/** Display formatting. Missing values render as an em dash, never as zero. */

const DASH = "—";
const DAY = 86_400_000;

export function formatInt(v: number | null | undefined): string {
  return v == null ? DASH : Math.round(v).toLocaleString("en-US");
}

export function formatCompact(v: number | null | undefined): string {
  if (v == null) return DASH;
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

/** 0.0767 → "7.7%" */
export function formatPct(v: number | null | undefined, digits = 1): string {
  return v == null ? DASH : `${(v * 100).toFixed(digits)}%`;
}

/** Signed value with a true minus sign: +1.2 / −0.4 / ±0.0 */
export function formatSigned(v: number, digits = 1, suffix = ""): string {
  const abs = Math.abs(v).toFixed(digits);
  const sign = Number(abs) === 0 ? "±" : v > 0 ? "+" : "−";
  return `${sign}${abs}${suffix}`;
}

/** "2026-10-12" → "12 Oct 2026" */
export function formatWeek(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** ISO week label, e.g. "2026-W42". */
export function isoWeekLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  const thursday = new Date(d.getTime() + (3 - ((d.getUTCDay() + 6) % 7)) * DAY);
  const yearStart = Date.UTC(thursday.getUTCFullYear(), 0, 1);
  const week = Math.ceil(((thursday.getTime() - yearStart) / DAY + 1) / 7);
  return `${thursday.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

export function addWeeks(iso: string, n: number): string {
  return new Date(Date.parse(`${iso}T00:00:00Z`) + n * 7 * DAY).toISOString().slice(0, 10);
}

export function weeksBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / (7 * DAY));
}

/** Monday of the ISO week containing `iso`. */
export function mondayOf(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return new Date(d.getTime() - ((d.getUTCDay() + 6) % 7) * DAY).toISOString().slice(0, 10);
}

export function windowLabel(w: { start: string; end: string; weeks: number }): string {
  return w.weeks === 1 ? `Week of ${formatWeek(w.end)}` : `${formatWeek(w.start)} – ${formatWeek(w.end)}`;
}
