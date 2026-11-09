"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { QueryError } from "@/components/common/query-state";
import { SeverityBadge } from "@/components/hotspots/hotspots-view";
import { useCountryDetection } from "@/hooks/use-detection";
import { useCountryTimeseries } from "@/hooks/use-surveillance";
import {
  ANOMALY_RING,
  GI_LABEL,
  GI_SCALE,
  giClass,
  MORAN_LABEL,
  RISK_INDEX,
  RISK_SCALE,
} from "@/lib/detection-scale";
import { addWeeks, formatPct, formatSigned, formatWeek } from "@/lib/format";
import type { AnomalyItem, CountryDetection, HotspotItem, HotspotStatus, Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

function Shell({ title, subtitle, children, actions }: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>}
        </div>
        {actions}
      </div>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Row({ k, v, className }: { k: string; v: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-3", className)}>
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="metric text-right">{v}</dd>
    </div>
  );
}

/** Risk level + the MEM thresholds behind it. */
export function RiskCard({ iso3 }: { iso3: string }) {
  const q = useCountryDetection(iso3);
  const d = q.data;
  const r = d?.risk;
  const t = d?.thresholds;
  return (
    <Shell title="Risk" subtitle="2-week forecast against the season's Moving Epidemic Method levels">
      {q.error && <QueryError error={q.error} />}
      {d && !d.run && <p className="text-xs text-muted-foreground">No detection run yet.</p>}
      {d?.run && (
        <div className="space-y-1.5 text-xs">
          {r ? (
            <>
              <div className="flex items-center gap-2">
                <span
                  className="size-2.5 rounded-[2px]"
                  style={{ background: RISK_SCALE.colors[RISK_INDEX[r.risk_level]] }}
                  aria-hidden
                />
                <span className="text-sm font-semibold">{RISK_SCALE.labels[RISK_INDEX[r.risk_level]]}</span>
                <span className="text-[11px] text-muted-foreground">for {formatWeek(r.target_week)}</span>
              </div>
              <dl>
                <Row
                  k="Forecast (80%)"
                  v={`${formatPct(r.forecast_point)} (${formatPct(r.forecast_lo80, 0)}–${formatPct(r.forecast_hi80, 0)})`}
                />
              </dl>
            </>
          ) : (
            <p className="text-muted-foreground">
              Not assessed: {d.thresholds_reason ?? "no 2-week forecast for this country this week"}.
            </p>
          )}
          {t && !t.quality_note && (
            <div className="space-y-1 border-t border-border pt-1.5">
              <dl className="space-y-1">
                <Row k={`Epidemic threshold (${t.season})`} v={formatPct(t.epidemic_threshold)} />
                <Row k="Medium / high / very high" v={`${formatPct(t.medium, 0)} / ${formatPct(t.high, 0)} / ${formatPct(t.very_high, 0)}`} />
              </dl>
              <p className="text-[10.5px] text-muted-foreground">
                From {t.n_seasons_used} past seasons ({t.seasons_used[0]} – {t.seasons_used[t.seasons_used.length - 1]}), COVID seasons excluded.
              </p>
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}

function classOf(h: HotspotStatus): number {
  return giClass(h as unknown as HotspotItem);
}

/** Current Gi* / Local Moran status and the weekly class strip. */
export function HotspotCard({ iso3 }: { iso3: string }) {
  const q = useCountryDetection(iso3);
  const d = q.data;
  const hs = d?.hotspots ?? [];
  const ref = d?.meta.reference_week;
  const current = hs.find((h) => h.window_end === ref) ?? hs[hs.length - 1];
  const strip = hs.slice(-52);
  return (
    <Shell
      title="Hotspot status"
      subtitle="Gi* and Local Moran on 4-week positivity relative to neighbouring countries"
      actions={
        <Link href="/hotspots" className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          Hotspots <ArrowRight className="size-3.5" />
        </Link>
      }
    >
      {q.error && <QueryError error={q.error} />}
      {d && !current && (
        <p className="text-xs text-muted-foreground">
          Not part of the hotspot analysis: no boundary polygon or fewer than 10 specimens in recent 4-week windows.
        </p>
      )}
      {current && (
        <>
          <dl className="space-y-1.5 text-xs">
            <Row k={`Window to ${formatWeek(current.window_end)}`} v={formatPct(current.value)} />
            <Row
              k="Gi*"
              v={`${GI_LABEL[current.gi_star.classification]} · z ${formatSigned(current.gi_star.z_score, 2)} · p(FDR) ${current.gi_star.p_fdr.toFixed(3)}`}
            />
            <Row k="Local Moran" v={MORAN_LABEL[current.local_moran.classification]} />
            <Row k="Neighbours" v={`${current.n_neighbours} (${current.neighbour_source === "queen" ? "shared border" : "4 nearest"})`} />
          </dl>
          <div className="mt-3">
            <div className="flex h-3 gap-px" role="img" aria-label="Weekly Gi* class over the last year">
              {strip.map((h) => (
                <span
                  key={h.window_end}
                  className="flex-1 rounded-[1px]"
                  style={{ background: GI_SCALE.colors[classOf(h)] }}
                  title={`${formatWeek(h.window_end)}: ${GI_SCALE.labels[classOf(h)]}`}
                />
              ))}
            </div>
            <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
              <span>{formatWeek(strip[0]?.window_end)}</span>
              <span>Gi* class per week</span>
              <span>{formatWeek(strip[strip.length - 1]?.window_end)}</span>
            </div>
          </div>
        </>
      )}
    </Shell>
  );
}

const SEVERITY_SIZE: Record<Severity, number> = { moderate: 8, high: 11, severe: 14 };

/** Weekly positivity over the last year with flagged weeks marked. */
export function AnomalyTimeline({ iso3 }: { iso3: string }) {
  const q = useCountryDetection(iso3);
  const d = q.data;
  const latest = d?.meta.latest_week;
  const from = latest ? addWeeks(latest, -51) : null;
  const ts = useCountryTimeseries(latest ? iso3 : null, from ?? "", latest ?? "");
  const primary = (d?.anomalies ?? []).filter((a) => a.method === "seasonal_ewma");
  const secondary = (d?.anomalies ?? []).filter((a) => a.method === "isolation_forest");

  return (
    <Shell
      title="Anomalies"
      subtitle="Last 52 weeks. Flagged when positivity is above the seasonal upper band (90th percentile of the same weeks in the latest 5 non-COVID years) and the EWMA control chart signals."
    >
      {(q.error || ts.error) && <QueryError error={(q.error ?? ts.error) as Error} />}
      {d && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="h-56">
            {ts.data && <TimelineChart points={ts.data.points} anomalies={primary} />}
          </div>
          <div className="text-xs">
            {primary.length === 0 ? (
              <p className="text-muted-foreground">No anomalous weeks in the last 52 weeks.</p>
            ) : (
              <AnomalyTable rows={primary} />
            )}
            {secondary.length > 0 && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                Isolation Forest (secondary signal, not used for alerts) also marks{" "}
                {secondary.map((a) => formatWeek(a.week_start)).join(", ")}.
              </p>
            )}
          </div>
        </div>
      )}
    </Shell>
  );
}

function AnomalyTable({ rows }: { rows: AnomalyItem[] }) {
  return (
    <div className="max-h-56 overflow-y-auto">
      <table className="w-full text-[11px]">
        <thead className="sticky top-0 bg-card text-muted-foreground">
          <tr className="border-b border-border">
            <th className="py-1 text-left font-normal">Week</th>
            <th className="py-1 text-right font-normal">Observed</th>
            <th className="py-1 text-right font-normal">Expected</th>
            <th className="py-1 text-right font-normal">Upper</th>
            <th className="py-1 pl-2 text-right font-normal">Severity</th>
          </tr>
        </thead>
        <tbody className="metric">
          {rows.map((a) => (
            <tr key={a.week_start} className="border-b border-border/60 last:border-0">
              <td className="py-1">
                {formatWeek(a.week_start)}
                {a.is_provisional && <span className="ml-1 text-[10px] text-status-warn">prov.</span>}
              </td>
              <td className="py-1 text-right">{formatPct(a.observed)}</td>
              <td className="py-1 text-right text-muted-foreground">{formatPct(a.expected)}</td>
              <td className="py-1 text-right text-muted-foreground">{formatPct(a.upper_band)}</td>
              <td className="py-1 pl-2 text-right">{a.severity && <SeverityBadge s={a.severity} />}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TimelineChart({
  points,
  anomalies,
}: {
  points: { week_start: string; positivity: number | null; specimens_tested: number | null; is_provisional: boolean }[];
  anomalies: AnomalyItem[];
}) {
  const option = useMemo<EChartsOption>(() => {
    const weeks = points.map((p) => p.week_start);
    const byWeek = new Map(anomalies.map((a) => [a.week_start, a]));
    const firstProv = points.find((p) => p.is_provisional)?.week_start;
    return {
      animation: false,
      grid: { left: 40, right: 16, top: 16, bottom: 28 },
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        formatter: (ps: { dataIndex: number }[]) => {
          const p = points[ps[0]?.dataIndex ?? 0];
          const a = byWeek.get(p.week_start);
          const extra = a
            ? `<div>Expected ${formatPct(a.expected)} · upper ${formatPct(a.upper_band)}</div><div>Anomaly: ${a.severity}</div>`
            : "";
          return `<div style="font-weight:600">Week of ${formatWeek(p.week_start)}${p.is_provisional ? " (provisional)" : ""}</div><div>Positivity ${formatPct(p.positivity)}</div>${extra}`;
        },
      },
      xAxis: {
        type: "category",
        data: weeks,
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: (v: string) => formatWeek(v) },
      },
      yAxis: {
        type: "value",
        min: 0,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10, formatter: (v: number) => `${Math.round(v * 100)}%` },
      },
      series: [
        {
          name: "Positivity",
          type: "line",
          data: points.map((p) => ((p.specimens_tested ?? 0) >= 10 ? p.positivity : null)),
          connectNulls: false,
          showSymbol: false,
          lineStyle: { width: 2, color: CHART.series },
          markArea: firstProv
            ? { silent: true, itemStyle: { color: CHART.provisional }, data: [[{ xAxis: firstProv }, { xAxis: weeks[weeks.length - 1] }]] }
            : undefined,
        },
        {
          name: "Anomaly",
          type: "scatter",
          data: points.map((p) => {
            const a = byWeek.get(p.week_start);
            return a ? { value: a.observed, symbolSize: SEVERITY_SIZE[a.severity ?? "moderate"] } : null;
          }),
          itemStyle: { color: "transparent", borderColor: ANOMALY_RING, borderWidth: 2 },
          z: 5,
        },
      ],
    };
  }, [points, anomalies]);
  return <EChart option={option} ariaLabel="Weekly positivity over the last year with anomalous weeks circled" />;
}

export type { CountryDetection };
