"use client";

import { ArrowRight, Info } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { Provenance } from "@/components/common/provenance";
import { QueryError } from "@/components/common/query-state";
import { type FillMode, useDetectionLayers } from "@/components/detection/globe-layers";
import { Globe } from "@/components/globe";
import { PageHeader } from "@/components/layout/page-header";
import { Switch } from "@/components/ui/switch";
import { useElementHeight, useMediaQuery } from "@/hooks/use-element-size";
import { useAnomalies, useDetectionHistory, useHotspots } from "@/hooks/use-detection";
import {
  COLD,
  GI_LABEL,
  GI_SCALE,
  giClass,
  HOT,
  MORAN_LABEL,
  OUTLIER,
  SEVERITY_LABEL,
} from "@/lib/detection-scale";
import { useFilters } from "@/lib/filters";
import { formatInt, formatPct, formatSigned, formatWeek } from "@/lib/format";
import type { AnomalyItem, HotspotItem, Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

const ANOMALY_LINE = OUTLIER;

function Card({ title, subtitle, children, className, actions }: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}) {
  return (
    <section className={cn("panel p-4", className)}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>}
        </div>
        {actions}
      </header>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function pText(p: number): string {
  return p <= 0.001 ? "≤ 0.001" : p.toFixed(3);
}

export function HotspotsView() {
  const [filters, setFilters] = useFilters();
  const router = useRouter();
  const [mode, setMode] = useState<Extract<FillMode, "hotspots" | "moran">>("hotspots");
  const [rings, setRings] = useState(true);
  // Centre the globe beside the controls (above them on phones, where they sit below it).
  const [controls, setControls] = useState<HTMLDivElement | null>(null);
  const controlsHeight = useElementHeight(controls);
  const roomBeside = useMediaQuery("(min-width: 640px)");
  const globeInsets = roomBeside ? { left: 252 } : { bottom: controlsHeight ? controlsHeight + 12 : 0 };
  const hotspots = useHotspots({ to: filters.to, region: filters.region });
  const anomalies = useAnomalies({ to: filters.to, weeks: filters.weeks, region: filters.region });
  const history = useDetectionHistory(filters.region);
  const layers = useDetectionLayers(mode, rings, filters);
  const h = hotspots.data;
  const meta = h?.meta ?? anomalies.data?.meta;

  const description = h?.window
    ? `Hotspots: 4-week window ${formatWeek(h.window.start)} – ${formatWeek(h.window.end)}. Anomalies: ${anomalies.data ? `${formatWeek(anomalies.data.window.start)} – ${formatWeek(anomalies.data.window.end)}` : "…"}.`
    : "Spatial clusters of test positivity and weeks unusually high for the time of year.";

  if (h && !h.run) {
    return (
      <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
        <PageHeader title="Hotspots & Anomalies" description="No detection run yet. Run `ei detect run`." />
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader title="Hotspots & Anomalies" description={description} />
      {h?.window?.includes_provisional && (
        <p className="rounded-md border border-status-warn/40 bg-status-warn/10 px-3 py-2 text-xs">
          The hotspot window includes provisional weeks; values may change as countries finish reporting.
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section className="relative overflow-hidden rounded-xl border border-border pt-[340px] sm:min-h-[520px] sm:pt-0">
          <Globe
            className="absolute inset-0"
            insets={globeInsets}
            pitch={0}
            autoRotate={false}
            fill={layers.fill}
            rings={layers.rings}
            hoverDetail={layers.hoverDetail}
            onCountryClick={(c) => router.push(`/countries/${c.iso3}`)}
          />
          <div ref={setControls} className="panel-glass relative m-3 space-y-2.5 rounded-lg p-2.5 sm:absolute sm:left-3 sm:top-3 sm:m-0 sm:w-60">
            <div className="grid grid-cols-2 gap-1 rounded-full border border-border bg-muted p-1 text-xs" role="radiogroup" aria-label="Statistic">
              {(["hotspots", "moran"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={mode === m}
                  onClick={() => setMode(m)}
                  className={cn(
                    "rounded-full px-3 py-1 transition-colors",
                    mode === m ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {m === "hotspots" ? "Gi*" : "Local Moran"}
                </button>
              ))}
            </div>
            <label htmlFor="hs-rings" className="flex items-center justify-between gap-3 text-xs">
              Anomaly rings
              <Switch id="hs-rings" checked={rings} onCheckedChange={setRings} />
            </label>
            <div className="max-h-[300px] overflow-y-auto border-t border-border pt-2">{layers.legend}</div>
          </div>
          {layers.error && (
            <QueryError error={layers.error} className="absolute bottom-3 left-3 rounded bg-card/90 p-2 text-xs text-status-error" />
          )}
        </section>

        <HotspotTable data={h?.items} error={hotspots.error} mode={mode} />
      </div>

      <Card
        title="History"
        subtitle="Countries per week in a Gi* hot or cold spot (FDR < 0.05, 4-week windows) and with a seasonal-EWMA anomaly. Click a week to inspect it."
      >
        {history.error && <QueryError error={history.error} />}
        <div className="h-60">
          {history.data && (
            <HistoryChart
              points={history.data.points}
              selected={h?.window?.end ?? null}
              onSelect={(week) => setFilters({ to: week === h?.meta.reference_week ? null : week })}
            />
          )}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <AnomalyFeed items={anomalies.data?.items} error={anomalies.error} weeks={filters.weeks} />
        <SecondarySignals items={anomalies.data?.items} />
      </div>

      <Methods
        weights={h?.weights_spec ?? null}
        permutations={h?.permutations ?? 999}
        alpha={h?.fdr_alpha ?? 0.05}
        anomalyNote={anomalies.data?.method_note ?? null}
        run={h?.run ?? null}
      />
      {meta && <Provenance meta={meta} />}
    </div>
  );
}

/* ---------- Hotspot table ---------- */

function HotspotTable({
  data,
  error,
  mode,
}: {
  data: HotspotItem[] | undefined;
  error: Error | null;
  mode: "hotspots" | "moran";
}) {
  const [showAll, setShowAll] = useState(false);
  const rows = useMemo(() => {
    const all = [...(data ?? [])];
    const key = (x: HotspotItem) => (mode === "hotspots" ? x.gi_star : x.local_moran);
    all.sort((a, b) => key(a).p_fdr - key(b).p_fdr || key(a).p_value - key(b).p_value || Math.abs(key(b).z_score) - Math.abs(key(a).z_score));
    return all;
  }, [data, mode]);
  const significant = rows.filter((r) => (mode === "hotspots" ? r.gi_star : r.local_moran).classification !== "ns");
  const shown = showAll ? rows : rows.slice(0, Math.max(12, significant.length));
  return (
    <Card
      title={mode === "hotspots" ? "Gi* results" : "Local Moran results"}
      subtitle={
        data
          ? `${significant.length} significant of ${rows.length} countries (FDR < 0.05). Sorted by FDR-adjusted p.`
          : "Loading…"
      }
    >
      {error && <QueryError error={error} />}
      {data && data.length === 0 && (
        <p className="text-xs text-muted-foreground">No hotspot results for this week. Pick a week in the history chart.</p>
      )}
      {data && data.length > 0 && (
        <>
          <div className="max-h-[400px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-card text-[11px] text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="py-1.5 text-left font-normal">Country</th>
                  <th className="py-1.5 text-right font-normal">Positivity</th>
                  <th className="py-1.5 pl-2 text-right font-normal">z</th>
                  <th className="py-1.5 pl-2 text-right font-normal">p</th>
                  <th className="py-1.5 pl-2 text-right font-normal">p (FDR)</th>
                  <th className="py-1.5 pl-2 text-left font-normal">Class</th>
                </tr>
              </thead>
              <tbody className="metric">
                {shown.map((r) => {
                  const s = mode === "hotspots" ? r.gi_star : r.local_moran;
                  const label = mode === "hotspots" ? GI_LABEL[s.classification] : MORAN_LABEL[s.classification];
                  const color = mode === "hotspots" ? GI_SCALE.colors[giClass(r)] : null;
                  return (
                    <tr key={r.iso3} className="border-b border-border/60 last:border-0">
                      <td className="py-1.5">
                        <Link href={`/countries/${r.iso3}`} className="hover:underline">
                          {r.name}
                        </Link>
                        {r.neighbour_source === "knn" && (
                          <span className="ml-1 text-[10px] text-muted-foreground" title="No land neighbour with data: 4 nearest countries used">
                            kNN
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 text-right">{formatPct(r.value)}</td>
                      <td className="py-1.5 pl-2 text-right">{formatSigned(s.z_score, 2)}</td>
                      <td className="py-1.5 pl-2 text-right text-muted-foreground">{pText(s.p_value)}</td>
                      <td className="py-1.5 pl-2 text-right">{pText(s.p_fdr)}</td>
                      <td className="py-1.5 pl-2">
                        <span className="flex items-center gap-1.5">
                          {color && <span className="size-2 shrink-0 rounded-[2px]" style={{ background: color }} />}
                          <span className={s.classification === "ns" ? "text-muted-foreground" : ""}>{label}</span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {rows.length > shown.length || showAll ? (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="mt-2 text-xs text-muted-foreground hover:text-foreground"
            >
              {showAll ? "Show fewer" : `Show all ${rows.length} countries`}
            </button>
          ) : null}
        </>
      )}
    </Card>
  );
}

/* ---------- History ---------- */

function HistoryChart({
  points,
  selected,
  onSelect,
}: {
  points: { week_start: string; hot: number; cold: number; anomalies: number; is_provisional: boolean }[];
  selected: string | null;
  onSelect: (week: string) => void;
}) {
  const option = useMemo<EChartsOption>(() => {
    const weeks = points.map((p) => p.week_start);
    const firstProv = points.find((p) => p.is_provisional)?.week_start;
    const series = [
      { name: "Hot spots", color: HOT, data: points.map((p) => p.hot) },
      { name: "Cold spots", color: COLD, data: points.map((p) => p.cold) },
      { name: "Anomalies", color: ANOMALY_LINE, data: points.map((p) => p.anomalies) },
    ];
    return {
      animation: false,
      grid: { left: 36, right: 16, top: 30, bottom: 28 },
      legend: { top: 0, left: 0, textStyle: { color: CHART.muted, fontSize: 11 }, itemWidth: 14, itemHeight: 2, icon: "rect" },
      tooltip: {
        trigger: "axis",
        ...CHART.tooltip,
        formatter: (ps: { seriesName: string; value: number; color: string; dataIndex: number }[]) => {
          const p = points[ps[0]?.dataIndex ?? 0];
          const rows = ps
            .map((x) => `<div style="display:flex;justify-content:space-between;gap:14px"><span><span style="display:inline-block;width:8px;height:2px;background:${x.color};margin-right:6px;vertical-align:middle"></span>${x.seriesName}</span><span>${x.value}</span></div>`)
            .join("");
          return `<div style="font-weight:600;margin-bottom:4px">Week of ${formatWeek(p.week_start)}${p.is_provisional ? " (provisional)" : ""}</div>${rows}<div style="color:${CHART.muted};margin-top:4px">Click to inspect this week</div>`;
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
        minInterval: 1,
        splitLine: { lineStyle: { color: CHART.grid } },
        axisLabel: { color: CHART.muted, fontSize: 10 },
      },
      series: series.map((s, i) => ({
        name: s.name,
        type: "line",
        data: s.data,
        showSymbol: false,
        lineStyle: { width: 2, color: s.color },
        itemStyle: { color: s.color },
        ...(i === 0
          ? {
              markArea: firstProv
                ? { silent: true, itemStyle: { color: CHART.provisional }, data: [[{ xAxis: firstProv }, { xAxis: weeks[weeks.length - 1] }]] }
                : undefined,
              markLine: selected
                ? {
                    silent: true,
                    symbol: "none",
                    lineStyle: { color: CHART.ink, type: "dashed", width: 1 },
                    label: { formatter: "Selected", color: CHART.muted, fontSize: 10, position: "insideEndTop" },
                    data: [{ xAxis: selected }],
                  }
                : undefined,
            }
          : {}),
      })),
    };
  }, [points, selected]);

  return (
    <EChart
      option={option}
      ariaLabel="Weekly number of countries in hot spots, cold spots and with anomalies"
      onAxisClick={(i) => {
        const p = points[Math.min(Math.max(i, 0), points.length - 1)];
        if (p) onSelect(p.week_start);
      }}
    />
  );
}

/* ---------- Anomalies ---------- */

const SEVERITY_TONE: Record<Severity, string> = {
  moderate: "border-border text-muted-foreground",
  high: "border-status-warn/50 text-status-warn",
  severe: "border-status-error/50 text-status-error",
};

export function SeverityBadge({ s }: { s: Severity }) {
  return <span className={cn("rounded border px-1.5 text-[10.5px]", SEVERITY_TONE[s])}>{SEVERITY_LABEL[s]}</span>;
}

function AnomalyFeed({ items, error, weeks }: { items: AnomalyItem[] | undefined; error: Error | null; weeks: number }) {
  const primary = (items ?? []).filter((a) => a.method === "seasonal_ewma");
  const byCountry = useMemo(() => {
    const m = new Map<string, AnomalyItem[]>();
    for (const a of primary) m.set(a.iso3, [...(m.get(a.iso3) ?? []), a]);
    return [...m.values()].sort((a, b) => Math.max(...b.map((x) => x.score)) - Math.max(...a.map((x) => x.score)));
  }, [primary]);
  return (
    <Card
      title="Anomaly feed"
      subtitle={`Seasonal EWMA, last ${weeks === 1 ? "week" : `${weeks} weeks`}: ${byCountry.length} countries, ${primary.length} country-weeks. Latest week first.`}
    >
      {error && <QueryError error={error} />}
      {items && byCountry.length === 0 && <p className="text-xs text-muted-foreground">No anomalies in this period.</p>}
      <ul className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
        {byCountry.map((rows) => {
          const latest = rows[0];
          return (
            <li key={latest.iso3} className="rounded-md border border-border/70 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <Link href={`/countries/${latest.iso3}`} className="flex items-center gap-1 text-xs font-medium hover:underline">
                  {latest.name} <ArrowRight className="size-3 text-muted-foreground" />
                </Link>
                <span className="text-[10.5px] text-muted-foreground">{latest.who_region}</span>
              </div>
              <table className="mt-1.5 w-full text-[11px]">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="text-left font-normal">Week</th>
                    <th className="text-right font-normal">Observed</th>
                    <th className="text-right font-normal">Expected</th>
                    <th className="text-right font-normal">Upper band</th>
                    <th className="pl-2 text-right font-normal">Severity</th>
                  </tr>
                </thead>
                <tbody className="metric">
                  {rows.map((a) => (
                    <tr key={a.week_start}>
                      <td>
                        {formatWeek(a.week_start)}
                        {a.is_provisional && <span className="ml-1 text-[10px] text-status-warn">prov.</span>}
                      </td>
                      <td className="text-right">{formatPct(a.observed)}</td>
                      <td className="text-right text-muted-foreground">{formatPct(a.expected)}</td>
                      <td className="text-right text-muted-foreground">{formatPct(a.upper_band)}</td>
                      <td className="pl-2 text-right">{a.severity && <SeverityBadge s={a.severity} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function SecondarySignals({ items }: { items: AnomalyItem[] | undefined }) {
  const rows = (items ?? []).filter((a) => a.method === "isolation_forest");
  return (
    <Card
      title="Secondary signal: Isolation Forest"
      subtitle="Weeks unusual for the country's own history in positivity, testing volume or week-on-week change. Shown for context only; never used for alerts."
    >
      {items && rows.length === 0 && <p className="text-xs text-muted-foreground">No unusual weeks in this period.</p>}
      {rows.length > 0 && (
        <div className="max-h-[420px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-card text-[11px] text-muted-foreground">
              <tr className="border-b border-border">
                <th className="py-1.5 text-left font-normal">Country</th>
                <th className="py-1.5 text-left font-normal">Week</th>
                <th className="py-1.5 text-right font-normal">Positivity</th>
                <th className="py-1.5 text-right font-normal">Specimens</th>
                <th className="py-1.5 pl-2 text-right font-normal">Score</th>
              </tr>
            </thead>
            <tbody className="metric">
              {rows.map((a) => (
                <tr key={`${a.iso3}-${a.week_start}`} className="border-b border-border/60 last:border-0">
                  <td className="py-1.5">
                    <Link href={`/countries/${a.iso3}`} className="hover:underline">
                      {a.name}
                    </Link>
                  </td>
                  <td className="py-1.5 text-muted-foreground">{formatWeek(a.week_start)}</td>
                  <td className="py-1.5 text-right">{formatPct(a.observed)}</td>
                  <td className="py-1.5 text-right">{formatInt(a.specimens_tested)}</td>
                  <td className="py-1.5 pl-2 text-right text-muted-foreground">{a.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/* ---------- Methods ---------- */

function Methods({
  weights,
  permutations,
  alpha,
  anomalyNote,
  run,
}: {
  weights: string | null;
  permutations: number;
  alpha: number;
  anomalyNote: string | null;
  run: { run_key: string; finished_at: string | null } | null;
}) {
  return (
    <section className="panel p-4 text-xs text-muted-foreground">
      <h2 className="flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Info className="size-4" aria-hidden /> Methods
      </h2>
      <dl className="mt-2 grid gap-x-6 gap-y-2 md:grid-cols-2">
        <div>
          <dt className="text-foreground">Hotspots</dt>
          <dd>
            Input: pooled positivity over 4 weeks per country (≥ 10 specimens); countries without data do not take part and
            are shown as “no data”, never “cold”. Weights: {weights ?? "—"}. Getis-Ord Gi* and Local Moran&apos;s I with
            conditional permutation inference ({formatInt(permutations)} permutations, ties counted against significance),
            Benjamini–Hochberg FDR at {alpha}. With about 130 countries, few pass the FDR correction; uncorrected p &lt; 0.05 is
            shown in a lighter tone and is suggestive only.
          </dd>
        </div>
        <div>
          <dt className="text-foreground">Anomalies</dt>
          <dd>{anomalyNote ?? "—"} Severity from the standardised residual: &lt; 3 moderate, 3–5 high, ≥ 5 severe.</dd>
        </div>
      </dl>
      {run && (
        <p className="mt-2 text-[11px]">
          Detection run {run.run_key}
          {run.finished_at ? `, finished ${new Date(run.finished_at).toLocaleString("en-GB")}` : ""}.
        </p>
      )}
    </section>
  );
}
