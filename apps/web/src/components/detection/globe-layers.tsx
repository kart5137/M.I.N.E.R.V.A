"use client";

import { useMemo } from "react";

import type { GlobeFill, GlobeRing } from "@/components/globe";
import { useAnomalies, useGlobalForecasts, useHotspots, useRisk } from "@/hooks/use-detection";
import {
  ANOMALY_RING,
  CHANGE_LEGEND_ORDER,
  CHANGE_SCALE,
  changeClass,
  type ClassScale,
  GI_LABEL,
  GI_LEGEND_ORDER,
  GI_SCALE,
  giClass,
  MORAN_LABEL,
  MORAN_SCALE,
  moranClass,
  RISK_INDEX,
  RISK_SCALE,
  SEVERITY_LABEL,
  SEVERITY_RADIUS,
} from "@/lib/detection-scale";
import type { Filters } from "@/lib/filters";
import { formatPct, formatSigned, formatWeek } from "@/lib/format";
import type { Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

export type FillMode = "positivity" | "hotspots" | "moran" | "risk" | "forecast_change";

export const FILL_MODES: { key: FillMode; label: string }[] = [
  { key: "positivity", label: "Test positivity" },
  { key: "hotspots", label: "Hot/cold spots (Gi*)" },
  { key: "moran", label: "Clusters (Local Moran)" },
  { key: "risk", label: "Risk level" },
  { key: "forecast_change", label: "Forecast change" },
];

export interface DetectionLayers {
  fill: GlobeFill | null;
  rings: GlobeRing[];
  hoverDetail: (iso3: string) => React.ReactNode;
  legend: React.ReactNode;
  /** What the fill shows and for which period (null for positivity). */
  note: string | null;
  error: Error | null;
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{k}</span>
      <span className="metric text-right text-foreground">{v}</span>
    </div>
  );
}

function pText(p: number): string {
  return p <= 0.001 ? "≤ 0.001" : p.toFixed(3);
}

/**
 * Data, colours, rings and hover lines for the detection layers on the globe. Hotspots
 * and anomalies follow the time filter; risk and forecast change are the latest run.
 */
export function useDetectionLayers(mode: FillMode, showAnomalies: boolean, filters: Filters): DetectionLayers {
  const spatial = mode === "hotspots" || mode === "moran";
  const hotspots = useHotspots({ to: filters.to, region: filters.region }, spatial);
  const risk = useRisk(filters.region, mode === "risk");
  const change = useGlobalForecasts(2, filters.region, mode === "forecast_change");
  const anomalies = useAnomalies(
    { to: filters.to, weeks: filters.weeks, region: filters.region },
    showAnomalies,
  );

  return useMemo<DetectionLayers>(() => {
    const anomalyBy = new Map((showAnomalies ? anomalies.data?.by_country : undefined)?.map((a) => [a.iso3, a]) ?? []);
    const rings: GlobeRing[] = [...anomalyBy.values()].map((a) => ({
      iso3: a.iso3,
      radius: SEVERITY_RADIUS[a.max_severity],
    }));
    const anomalyLine = (iso3: string) => {
      const a = anomalyBy.get(iso3);
      if (!a) return null;
      return (
        <div className="mt-1.5 border-t border-border pt-1.5">
          <Row k="Anomaly" v={`${SEVERITY_LABEL[a.max_severity]} · ${a.weeks_flagged} wk`} />
          <Row k="Latest flagged" v={formatWeek(a.latest_week)} />
        </div>
      );
    };
    const anomalyLegend = showAnomalies ? (
      <AnomalyLegend weeks={anomalies.data?.window.weeks ?? filters.weeks} count={anomalyBy.size} />
    ) : null;
    const base = { rings, error: (anomalies.error as Error | null) ?? null };

    if (spatial) {
      const items = hotspots.data?.items ?? [];
      const byIso3 = new Map(items.map((h) => [h.iso3, h]));
      const isGi = mode === "hotspots";
      const fill: GlobeFill = {
        byIso3: new Map(items.map((h) => [h.iso3, isGi ? giClass(h) : moranClass(h)])),
        colors: (isGi ? GI_SCALE : MORAN_SCALE).colors,
      };
      const w = hotspots.data?.window;
      return {
        ...base,
        error: (hotspots.error as Error | null) ?? base.error,
        fill,
        note: w
          ? `4-week pooled positivity, ${formatWeek(w.start)} – ${formatWeek(w.end)} · ${items.length} countries`
          : hotspots.data
            ? `Hotspots are computed for windows ending ${formatWeek(hotspots.data.available_from)} – ${formatWeek(hotspots.data.available_to)}.`
            : null,
        hoverDetail: (iso3) => {
          const h = byIso3.get(iso3);
          return (
            <>
              <div className="mt-1.5 space-y-0.5">
                {h ? (
                  <>
                    <Row k="4-week positivity" v={formatPct(h.value)} />
                    {isGi ? (
                      <>
                        <Row k="Gi*" v={GI_LABEL[h.gi_star.classification]} />
                        <Row k="z (permutation)" v={formatSigned(h.gi_star.z_score, 2)} />
                        <Row k="p / p (FDR)" v={`${pText(h.gi_star.p_value)} / ${pText(h.gi_star.p_fdr)}`} />
                      </>
                    ) : (
                      <>
                        <Row k="Local Moran" v={MORAN_LABEL[h.local_moran.classification]} />
                        <Row k="p / p (FDR)" v={`${pText(h.local_moran.p_value)} / ${pText(h.local_moran.p_fdr)}`} />
                      </>
                    )}
                    <Row k="Neighbours" v={`${h.n_neighbours} (${h.neighbour_source === "queen" ? "shared border" : "nearest"})`} />
                  </>
                ) : (
                  <div className="text-muted-foreground">No data in this window</div>
                )}
              </div>
              {anomalyLine(iso3)}
            </>
          );
        },
        legend: (
          <>
            <ClassLegend
              title={isGi ? "Getis-Ord Gi* (4-week positivity)" : "Local Moran's I (FDR < 0.05)"}
              scale={isGi ? GI_SCALE : MORAN_SCALE}
              order={isGi ? GI_LEGEND_ORDER : [1, 2, 3, 0]}
              footnote={
                isGi
                  ? "Gi* describes a country together with its neighbours. 999 permutations; Benjamini–Hochberg FDR."
                  : "Clusters: country and neighbours alike. Outliers: country unlike its neighbours."
              }
            />
            {anomalyLegend}
          </>
        ),
      };
    }

    if (mode === "risk") {
      const items = risk.data?.items ?? [];
      const byIso3 = new Map(items.map((r) => [r.iso3, r]));
      const first = items[0];
      return {
        ...base,
        error: (risk.error as Error | null) ?? base.error,
        fill: { byIso3: new Map(items.map((r) => [r.iso3, RISK_INDEX[r.risk_level]])), colors: RISK_SCALE.colors },
        note: first
          ? `Latest forecast for ${formatWeek(first.target_week)} (2 weeks ahead) · ${items.length} countries assessed · does not follow the time slider`
          : null,
        hoverDetail: (iso3) => {
          const r = byIso3.get(iso3);
          return (
            <>
              <div className="mt-1.5 space-y-0.5">
                {r ? (
                  <>
                    <Row k="Risk" v={RISK_SCALE.labels[RISK_INDEX[r.risk_level]]} />
                    <Row k="2-week forecast" v={`${formatPct(r.forecast_point)} (${formatPct(r.forecast_lo80, 0)}–${formatPct(r.forecast_hi80, 0)})`} />
                    <Row k="Epidemic threshold" v={formatPct(r.thresholds.epidemic_threshold)} />
                    <Row k="High intensity" v={formatPct(r.thresholds.high)} />
                  </>
                ) : (
                  <div className="text-muted-foreground">Not assessed</div>
                )}
              </div>
              {anomalyLine(iso3)}
            </>
          );
        },
        legend: (
          <>
            <ClassLegend
              title="Risk: 2-week forecast vs MEM thresholds"
              scale={RISK_SCALE}
              order={[0, 1, 2]}
              noData="Not assessed"
              footnote="Temperate countries with ≥ 3 usable past seasons only."
            />
            {anomalyLegend}
          </>
        ),
      };
    }

    if (mode === "forecast_change") {
      const items = change.data?.items ?? [];
      const byIso3 = new Map(items.map((f) => [f.iso3, f]));
      const first = items[0];
      return {
        ...base,
        error: (change.error as Error | null) ?? base.error,
        fill: {
          byIso3: new Map(items.filter((f) => f.change_pp != null).map((f) => [f.iso3, changeClass(f.change_pp!)])),
          colors: CHANGE_SCALE.colors,
        },
        note: first
          ? `${change.data?.model_label}: ${formatWeek(first.origin_week)} → ${formatWeek(first.target_week)} · does not follow the time slider`
          : null,
        hoverDetail: (iso3) => {
          const f = byIso3.get(iso3);
          return (
            <>
              <div className="mt-1.5 space-y-0.5">
                {f ? (
                  <>
                    <Row k={`Observed ${formatWeek(f.origin_week)}`} v={formatPct(f.origin_value)} />
                    <Row k={`Forecast ${formatWeek(f.target_week)}`} v={formatPct(f.point)} />
                    <Row k="80% interval" v={`${formatPct(f.lo80, 0)}–${formatPct(f.hi80, 0)}`} />
                    <Row k="Change" v={f.change_pp == null ? "—" : formatSigned(f.change_pp, 1, " pp")} />
                  </>
                ) : (
                  <div className="text-muted-foreground">No forecast</div>
                )}
              </div>
              {anomalyLine(iso3)}
            </>
          );
        },
        legend: (
          <>
            <ClassLegend
              title="Forecast change, 2 weeks ahead (pp)"
              scale={CHANGE_SCALE}
              order={CHANGE_LEGEND_ORDER}
              noData="No forecast"
              footnote="Point forecast minus the observed positivity in the origin week."
            />
            {anomalyLegend}
          </>
        ),
      };
    }

    return {
      ...base,
      fill: null,
      note: null,
      hoverDetail: (iso3) => anomalyLine(iso3),
      legend: anomalyLegend,
    };
  }, [mode, spatial, showAnomalies, hotspots.data, hotspots.error, risk.data, risk.error, change.data, change.error, anomalies.data, anomalies.error, filters.weeks]);
}

export function ClassLegend({
  title,
  scale,
  order,
  footnote,
  noData = "No data",
  className,
}: {
  title: string;
  scale: ClassScale;
  order: number[];
  footnote?: string;
  noData?: string;
  className?: string;
}) {
  return (
    <figure className={cn("space-y-1.5 text-[11px]", className)} aria-label={`${title} legend`}>
      <figcaption className="font-medium text-foreground">{title}</figcaption>
      <ul className="space-y-1">
        {order.map((i) => (
          <li key={i} className="flex items-center gap-2 text-muted-foreground">
            <span className="size-2.5 shrink-0 rounded-[2px]" style={{ background: scale.colors[i] }} />
            {scale.labels[i]}
          </li>
        ))}
        <li className="flex items-center gap-2 text-muted-foreground">
          <span className="size-2.5 shrink-0 rounded-[2px] border border-[var(--globe-border)] bg-[var(--globe-land)]" />
          {noData}
        </li>
      </ul>
      {footnote && <p className="text-[10.5px] leading-snug text-muted-foreground/80">{footnote}</p>}
    </figure>
  );
}

function AnomalyLegend({ weeks, count }: { weeks: number; count: number }) {
  const sizes: Severity[] = ["moderate", "high", "severe"];
  return (
    <figure className="mt-2 space-y-1.5 border-t border-border pt-2 text-[11px]" aria-label="Anomaly legend">
      <figcaption className="font-medium text-foreground">
        Anomalies, last {weeks} wk <span className="font-normal text-muted-foreground">· {count} countries</span>
      </figcaption>
      <div className="flex items-end gap-3 text-muted-foreground">
        {sizes.map((s, i) => (
          <span key={s} className="flex items-center gap-1.5">
            <span
              className="inline-block rounded-full border-2"
              style={{ borderColor: ANOMALY_RING, width: 8 + i * 4, height: 8 + i * 4 }}
            />
            {SEVERITY_LABEL[s]}
          </span>
        ))}
      </div>
      <p className="text-[10.5px] leading-snug text-muted-foreground/80">
        Ring size = highest severity: positivity above the seasonal upper band with an EWMA signal.
      </p>
    </figure>
  );
}
