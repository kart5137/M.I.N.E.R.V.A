import { type CountMeasure, countBins } from "@/lib/count-scale";
import { POSITIVITY_BINS } from "@/lib/positivity-scale";
import { cn } from "@/lib/utils";

/** Legend for the "Total cases" / "Total detections" fill (weekly counts). */
export function CountLegend({
  measure,
  title,
  palette = null,
  className,
}: {
  measure: CountMeasure;
  title: string;
  /** The disease's colour ramp; default: the influenza amber steps. */
  palette?: readonly string[] | null;
  className?: string;
}) {
  return (
    <figure className={cn("space-y-2 text-[11px]", className)} aria-label="Map legend">
      <figcaption className="font-medium text-foreground">{title} a week (average)</figcaption>
      <div className="flex">
        {countBins(measure).map((b, i) => (
          <div key={b.label} className="flex-1">
            <div
              className="h-2.5 border-r-2 border-card last:border-r-0"
              style={{ background: palette?.[i] ?? POSITIVITY_BINS[i].color }}
            />
            <div className="metric mt-1 text-center text-[10px] text-muted-foreground">{b.label}</div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <span className="size-2.5 rounded-[2px] border border-[var(--globe-border)] bg-[var(--globe-land)]" />
        No report
      </div>
      <p className="text-[10.5px] leading-snug text-muted-foreground">
        Totals grow with population: a large country can be dark here with a low rate. Switch to
        the per-100,000 fill to compare risk.
      </p>
    </figure>
  );
}
