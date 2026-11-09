"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { QueryError } from "@/components/common/query-state";
import { useCountryForecasts } from "@/hooks/use-forecasts";
import { formatPct, formatWeek } from "@/lib/format";

/** Active-model forecasts for one country (Country Intelligence page). */
export function ForecastSummary({ iso3 }: { iso3: string }) {
  const fc = useCountryForecasts(iso3);
  const d = fc.data;
  const active = (d?.forecasts ?? []).filter((f) => f.is_active);
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium">Forecast</h2>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Test positivity, active model per horizon, with 80% intervals
          </p>
        </div>
        <Link
          href={`/predictions?country=${iso3}`}
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
                <span className="font-medium">{formatPct(f.point)}</span>
                <span className="ml-1.5 text-[11px] text-muted-foreground">
                  {formatPct(f.lo80, 0)}–{formatPct(f.hi80, 0)}
                </span>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
