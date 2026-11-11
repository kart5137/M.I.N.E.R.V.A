import {
  FEW_SPECIMENS_COLOR,
  MIN_SPECIMENS,
  POSITIVITY_BINS,
} from "@/lib/positivity-scale";
import { elevationNote } from "@/components/globe/elevation";
import { cn } from "@/lib/utils";

export function PositivityLegend({
  showDetections = false,
  hideScale = false,
  className,
}: {
  showDetections?: boolean;
  /** Only the detections key (another layer owns the fill). */
  hideScale?: boolean;
  className?: string;
}) {
  if (hideScale) {
    return showDetections ? (
      <div className={cn("flex items-center gap-1.5 text-[11px] text-muted-foreground", className)}>
        <span className="h-2 w-3 rounded-[2px] border-t-2 border-[var(--globe-hover)] bg-[var(--globe-land)]" />
        {elevationNote("positivity")}
      </div>
    ) : null;
  }
  return (
    <figure className={cn("space-y-2 text-[11px]", className)} aria-label="Map legend">
      <figcaption className="font-medium text-foreground">Influenza test positivity (%)</figcaption>
      <div className="flex">
        {POSITIVITY_BINS.map((b) => (
          <div key={b.label} className="flex-1">
            <div className="h-2.5 border-r-2 border-card last:border-r-0" style={{ background: b.color }} />
            <div className="metric mt-1 text-center text-[10px] text-muted-foreground">{b.label}</div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px]" style={{ background: FEW_SPECIMENS_COLOR }} />
          &lt; {MIN_SPECIMENS} specimens
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] border border-[var(--globe-border)] bg-[var(--globe-land)]" />
          No report
        </span>
      </div>
      {showDetections && (
        <div className="flex items-center gap-1.5 border-t border-border pt-2 text-muted-foreground">
          <span className="h-2 w-3 rounded-[2px] border-t-2 border-[var(--globe-hover)] bg-[var(--globe-land)]" />
          {elevationNote("positivity")}
        </div>
      )}
    </figure>
  );
}
