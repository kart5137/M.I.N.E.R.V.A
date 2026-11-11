import { INCIDENCE_BINS } from "@/lib/incidence-scale";
import { FEW_SPECIMENS_COLOR } from "@/lib/positivity-scale";
import { cn } from "@/lib/utils";

/** Legend for reported dengue incidence (case-based diseases). */
export function IncidenceLegend({
  disease = "Dengue",
  palette = null,
  className,
}: {
  disease?: string;
  /** The disease's colour ramp (lib/disease-palette.ts); default: the dengue bins' colours. */
  palette?: readonly string[] | null;
  className?: string;
}) {
  return (
    <figure className={cn("space-y-2 text-[11px]", className)} aria-label="Map legend">
      <figcaption className="font-medium text-foreground">
        {disease} cases per 100,000 per week
      </figcaption>
      <div className="flex">
        {INCIDENCE_BINS.map((b, i) => (
          <div key={b.label} className="flex-1">
            <div className="h-2.5 border-r-2 border-card last:border-r-0" style={{ background: palette?.[i] ?? b.color }} />
            <div className="metric mt-1 text-center text-[10px] text-muted-foreground">{b.label}</div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px]" style={{ background: FEW_SPECIMENS_COLOR }} />
          No population figure
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] border border-[var(--globe-border)] bg-[var(--globe-land)]" />
          No report
        </span>
      </div>
      <p className="text-[10.5px] leading-snug text-muted-foreground">
        Case definitions differ by country; compare a country with itself over time.
      </p>
    </figure>
  );
}
