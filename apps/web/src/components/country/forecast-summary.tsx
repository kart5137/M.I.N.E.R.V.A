"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { QueryError } from "@/components/common/query-state";
import { useCountryForecasts } from "@/hooks/use-forecasts";
import { diseaseParam, useDisease, withParams } from "@/lib/filters";
import { formatWeek } from "@/lib/format";
import { metricFor } from "@/lib/metric";

/** Active-model forecasts for one country (Country Intelligence page). */
export function ForecastSummary({ iso3 }: { iso3: string }) {
  const fc = useCountryForecasts(iso3);
  const disease = useDisease();
  const m = metricFor(disease);
  const d = fc.data;
  const active = (d?.forecasts ?? []).filter((f) => f.is_active);
  return (
    <section className="panel p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium">Forecast</h2>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {m.key === "incidence" ? "Weekly incidence per 100,000" : "Test positivity"}, active model per horizon, with 80%
            intervals
          </p>
        </div>
        <Link
          href={withParams(`/predictions?country=${iso3}`, diseaseParam(disease))}
          className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          Prediction Center <ArrowRight className="size-3.5" />
        </Link>
      </div>
      {fc.error && <QueryError error={fc.error} />}
      {d && !d.eligible && <p className="mt-2 text-xs text-muted-foreground">{d.reason}</p>}
      {active.length > 0 && (
        <dl className="mt-2 space-y-1.5 text-xs">
          {active.map((f) => (
            <div key={f.id} className="flex items-baseline justify-between gap-3">
              <dt className="text-muted-foreground">
                {formatWeek(f.target_week)} <span className="text-[10.5px]">(+{f.horizon_weeks}, {f.label})</span>
              </dt>
              <dd className="metric">
                <span className="font-medium">{m.format(f.point)}</span>
                <span className="ml-1.5 text-[11px] text-muted-foreground">
                  {m.formatBound(f.lo80)}–{m.formatBound(f.hi80)}
                </span>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
