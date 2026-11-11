import {
  FEW_SPECIMENS_COLOR,
  MIN_SPECIMENS,
  POSITIVITY_BINS,
} from "@/lib/positivity-scale";
import { cn } from "@/lib/utils";

export function PositivityLegend({ className }: { className?: string }) {
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
    </figure>
  );
}
