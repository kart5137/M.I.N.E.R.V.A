"use client";

import { QueryError } from "@/components/common/query-state";
import { useScorecard } from "@/hooks/use-forecasts";
import { formatInt, formatPct, formatWeek } from "@/lib/format";
import type { Metric } from "@/lib/metric";
import type { HorizonScore } from "@/lib/types";
import { cn } from "@/lib/utils";

import { err, signedPct } from "./prediction-center";

function Row({ k, v, muted }: { k: string; v: string; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className={cn("metric text-right", muted && "text-muted-foreground")}>{v}</dd>
    </div>
  );
}

function HorizonTile({ h, m }: { h: HorizonScore; m: Metric }) {
  const e = err(m);
  return (
    <section className="rounded-lg border border-border/70 bg-background/40 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-medium">{h.horizon_weeks}-week horizon</h3>
        <span className="text-[11px] text-muted-foreground">{h.model_label}</span>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {formatInt(h.scored)} of {formatInt(h.published)} published forecasts scored · {formatInt(h.pending)} waiting
        {h.unscorable ? ` · ${formatInt(h.unscorable)} without a report` : ""}
      </p>
      <dl className="mt-2 space-y-1 text-xs">
        <Row k="Live MAE" v={e(h.mae)} />
        <Row k="Backtest MAE" v={e(h.backtest_mae)} muted />
        <Row k="Last value, live MAE" v={e(h.last_value_mae)} muted />
        <Row k="Skill vs last value" v={signedPct(h.skill_vs_last_value)} />
        <Row k="80% interval held" v={`${formatPct(h.coverage_80, 0)} (backtest ${formatPct(h.backtest_coverage_80, 0)})`} />
        <Row k="95% interval held" v={formatPct(h.coverage_95, 0)} />
      </dl>
    </section>
  );
}

/**
 * Live track record: the forecasts the dashboard published, scored once the weeks they
 * forecast were settled. Empty until the first target week settles; never estimated.
 */
export function LiveScorecard({ m }: { m: Metric }) {
  const q = useScorecard();
  const d = q.data;
  const scored = d?.horizons.reduce((n, h) => n + h.scored, 0) ?? 0;
  const pending = d?.horizons.reduce((n, h) => n + h.pending, 0) ?? 0;
  return (
    <section className="panel p-4">
      <h2 className="text-sm font-medium">Live track record</h2>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        {d?.rule ?? "Published forecasts scored against the values reported later."}
      </p>
      {q.error && <QueryError error={q.error} />}
      {d && d.horizons.length === 0 && (
        <p className="mt-3 text-xs text-muted-foreground">No forecasts have been published yet.</p>
      )}
      {d && d.horizons.length > 0 && scored === 0 && (
        <p className="mt-3 rounded-md border border-border bg-background/40 px-3 py-2 text-xs text-muted-foreground">
          No published forecast has reached a settled week yet, so there is no live score.{" "}
          {formatInt(pending)} forecasts are waiting; the first are scored once the week of{" "}
          {formatWeek(d.next_target_week)} is no longer provisional
          {m.key === "incidence" ? " (dengue reports settle about 8 weeks after the week)" : ""}. The record builds up
          from here, one forecast week at a time.
        </p>
      )}
      {d && scored > 0 && (
        <>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            {d.horizons.map((h) => <HorizonTile key={h.horizon_weeks} h={h} m={m} />)}
          </div>
          <h3 className="mt-4 text-xs font-medium">Latest scored forecasts</h3>
          <div className="mt-1 overflow-x-auto" tabIndex={0} role="region" aria-label="Latest scored forecasts">
            <table className="w-full min-w-[640px] text-xs">
              <thead className="text-[11px] text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="py-1.5 text-left font-normal">Country</th>
                  <th className="py-1.5 text-left font-normal">Week</th>
                  <th className="py-1.5 text-right font-normal">Horizon</th>
                  <th className="py-1.5 text-right font-normal">Forecast (80%)</th>
                  <th className="py-1.5 text-right font-normal">Reported</th>
                  <th className="py-1.5 text-right font-normal">Error</th>
                  <th className="py-1.5 text-right font-normal">In 80%</th>
                </tr>
              </thead>
              <tbody className="metric">
                {d.recent.slice(0, 12).map((r) => (
                  <tr key={`${r.iso3}-${r.origin_week}-${r.horizon_weeks}`} className="border-b border-border/60 last:border-0">
                    <td className="py-1.5">{r.name}</td>
                    <td className="py-1.5 text-muted-foreground">{formatWeek(r.target_week)}</td>
                    <td className="py-1.5 text-right text-muted-foreground">+{r.horizon_weeks} wk</td>
                    <td className="py-1.5 text-right">
                      {m.format(r.point)} ({m.formatBound(r.lo80)}–{m.formatBound(r.hi80)})
                    </td>
                    <td className="py-1.5 text-right">{m.format(r.actual)}</td>
                    <td className="py-1.5 text-right">{err(m)(r.abs_error)}</td>
                    <td className="py-1.5 text-right">{r.in_80 == null ? "—" : r.in_80 ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
