"use client";

import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { useAnnualSummary } from "@/hooks/use-annual";
import { DISEASES } from "@/lib/diseases";
import { useFilters } from "@/lib/filters";

/** About the Data for yearly diseases (malaria): source, measures, what it cannot show. */
export function AnnualAbout() {
  const [filters] = useFilters();
  const info = DISEASES[filters.disease];
  const q = useAnnualSummary(filters.disease, null);
  const d = q.data;
  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="About the Data"
        eyebrow={`${info.label} · yearly estimates`}
        description="Where every number comes from, how it is processed, and what it cannot tell you."
      />
      {q.error && <QueryError error={q.error} />}
      {d && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="panel p-4 text-xs">
            <h2 className="text-sm font-medium">Source</h2>
            <ul className="mt-2 space-y-1 text-muted-foreground">
              {d.meta.sources.map((s) => (
                <li key={s.key}>{s.attribution ?? s.name}</li>
              ))}
              <li>
                Years {d.meta.first_year}–{d.meta.latest_year}; loaded weekly from the WHO Global Health Observatory API,
                checked (no negative values, estimates inside their ranges, known countries) and stored as published.
              </li>
            </ul>
            <h2 className="mt-4 text-sm font-medium">Measures</h2>
            <dl className="mt-2 space-y-1">
              {Object.entries(d.measures).map(([k, label]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="font-mono text-[11px] text-muted-foreground">{k}</dt>
                  <dd className="text-right">{label}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="panel p-4 text-xs">
            <h2 className="text-sm font-medium">Limitations</h2>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-muted-foreground">
              {d.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
              <li>World and regional totals are WHO&apos;s own estimates, not sums of countries.</li>
              <li>Countries that are not malaria-endemic have no estimates; a zero means no indigenous cases.</li>
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
