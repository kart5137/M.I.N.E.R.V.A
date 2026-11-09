import { formatWeek } from "@/lib/format";
import type { ResponseMeta } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Source attribution and data currency, shown under every data view. */
export function Provenance({ meta, className }: { meta: ResponseMeta; className?: string }) {
  return (
    <p className={cn("text-[11px] leading-relaxed text-muted-foreground", className)}>
      {meta.demo && <span className="mr-2 rounded bg-status-warn px-1 font-semibold text-black">DEMO</span>}
      {meta.sources.map((s) => s.attribution ?? s.name).join(" ")} Reference week{" "}
      {formatWeek(meta.reference_week)}
      {meta.provisional_from && <> · weeks from {formatWeek(meta.provisional_from)} are provisional</>}.
    </p>
  );
}
