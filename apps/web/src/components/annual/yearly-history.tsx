"use client";

import { QueryError } from "@/components/common/query-state";
import { useAnnualSeries } from "@/hooks/use-annual";
import { useDisease } from "@/lib/filters";
import type { AnnualSeries } from "@/lib/types";

import { AnnualBandChart } from "./annual-chart";

/** Every year from the first to the last, so missing years show as gaps, never as zero. */
function fullRange(s: AnnualSeries): AnnualSeries["points"] {
  if (!s.points.length) return [];
  const by = new Map(s.points.map((p) => [p.year, p]));
  const first = s.points[0].year;
  const last = s.points[s.points.length - 1].year;
  return Array.from({ length: last - first + 1 }, (_, i) => by.get(first + i) ?? { year: first + i, values: {} });
}

/** Yearly reported cases and deaths: cholera's WHO yearly figures to 2016 and sums of the
 *  weekly reports from 2023 (the years in between left empty); COVID-19's weekly sums. */
export function YearlyHistory({ iso3 }: { iso3: string }) {
  const disease = useDisease();
  const q = useAnnualSeries(disease, iso3);
  const s = q.data;
  const pts = s ? fullRange(s) : [];
  const partial = s?.partial_year;
  return (
    <section className="panel p-4">
      <h2 className="text-sm font-medium">Reported cases and deaths by year</h2>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        {s?.notes.join(" ") ?? "Loading…"}
        {partial ? ` ${partial} is incomplete (reports so far).` : ""}
      </p>
      {q.error && <QueryError error={q.error} />}
      {s && pts.length === 0 && <p className="mt-2 text-xs text-muted-foreground">No yearly reports for this country.</p>}
      {pts.length > 0 && (
        <div className="mt-2 grid gap-4 lg:grid-cols-2">
          <div className="h-56">
            <AnnualBandChart points={pts} measure="reported_cases" label="Reported cases" highlight={partial ?? null} />
          </div>
          <div className="h-56">
            <AnnualBandChart points={pts} measure="reported_deaths" label="Reported deaths" highlight={partial ?? null} />
          </div>
        </div>
      )}
    </section>
  );
}
