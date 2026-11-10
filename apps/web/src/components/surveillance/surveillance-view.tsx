"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { SlidersHorizontal, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { QueryError } from "@/components/common/query-state";
import { Provenance } from "@/components/common/provenance";
import { FILL_MODES, type FillMode, useDetectionLayers } from "@/components/detection/globe-layers";
import { Globe, type GlobeLayers } from "@/components/globe";
import { Switch } from "@/components/ui/switch";
import { useElementHeight, useMediaQuery } from "@/hooks/use-element-size";
import { globalQueryOptions, useGlobalSurveillance } from "@/hooks/use-surveillance";
import { DISEASES } from "@/lib/diseases";
import { useFilters } from "@/lib/filters";
import { formatInt, windowLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CountryPanel } from "./country-panel";
import { IncidenceLegend } from "./incidence-legend";
import { PositivityLegend } from "./positivity-legend";
import { TimeSlider } from "./time-slider";

const FILL_PARAM = "fill";

function Toggle({
  id,
  label,
  checked,
  onChange,
  swatch,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  swatch?: React.ReactNode;
}) {
  return (
    <label htmlFor={id} className="flex items-center justify-between gap-4 text-xs">
      <span className="flex items-center gap-2 text-foreground">
        {swatch}
        {label}
      </span>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </label>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{children}</h2>;
}

export function SurveillanceView() {
  const [filters, setFilters] = useFilters();
  const params = useSearchParams();
  const selected = params.get("country")?.toUpperCase() ?? null;
  const setSelected = useCallback((iso3: string | null) => {
    const next = new URLSearchParams(window.location.search);
    if (iso3) next.set("country", iso3);
    else next.delete("country");
    window.history.replaceState(null, "", `?${next.toString()}`);
  }, []);

  const [projection, setProjection] = useState<"globe" | "mercator">("globe");
  // Small screens: the controls cover the globe, so they start closed behind a button.
  const [controlsOpen, setControlsOpen] = useState(false);
  const [autoRotate, setAutoRotate] = useState(!selected);
  const [detections, setDetections] = useState(true);
  const [showAnomalies, setShowAnomalies] = useState(params.get("anomalies") === "1");
  const fillParam = params.get(FILL_PARAM);
  const [fillMode, setFillModeState] = useState<FillMode | "none">(
    FILL_MODES.some((m) => m.key === fillParam) || fillParam === "none" ? (fillParam as FillMode | "none") : "positivity",
  );
  const setParam = useCallback((key: string, value: string | null) => {
    const next = new URLSearchParams(window.location.search);
    if (value) next.set(key, value);
    else next.delete(key);
    window.history.replaceState(null, "", `?${next.toString()}`);
  }, []);
  const setFillMode = (m: FillMode | "none") => {
    setFillModeState(m);
    setParam(FILL_PARAM, m === "positivity" ? null : m);
  };
  const info = DISEASES[filters.disease];
  // The "positivity" fill is the disease's primary measure: test positivity, or cases per
  // 100,000 for case-based diseases (dengue), which have the detection fills too (D4).
  const caseBased = info.caseBased;
  const activeFill: FillMode | "none" =
    !info.features.detection && fillMode !== "none" ? "positivity" : fillMode;
  const fillOptions: { key: FillMode | "none"; label: string }[] = [
    ...FILL_MODES.map((m) => (m.key === "positivity" && caseBased ? { ...m, label: "Cases per 100,000" } : m)),
    { key: "none", label: "None" },
  ];
  const anomaliesOn = showAnomalies && info.features.detection;
  const layers: GlobeLayers = { positivity: activeFill === "positivity", detections };
  const detection = useDetectionLayers(
    activeFill === "none" ? "positivity" : activeFill,
    anomaliesOn,
    filters,
  );

  const queryClient = useQueryClient();
  const global = useGlobalSurveillance(filters);
  const data = global.data;
  const valueByIso3 = useMemo(() => new Map(data?.countries.map((c) => [c.iso3, c]) ?? []), [data]);

  // Centre the globe in the area the overlays leave free.
  const [bottomBar, setBottomBar] = useState<HTMLDivElement | null>(null);
  const bottomHeight = useElementHeight(bottomBar);
  const wide = useMediaQuery("(min-width: 1024px)");
  const insets = {
    top: 0,
    left: wide ? 280 : 0,
    right: wide && selected && data ? 344 : 0,
    bottom: bottomHeight ? bottomHeight + 12 : 0,
  };

  const prefetch = useCallback(
    (week: string) => void queryClient.prefetchQuery(globalQueryOptions({ ...filters, to: week })),
    [queryClient, filters],
  );

  return (
    <div className="relative flex-1 overflow-hidden">
      <Globe
        className="absolute inset-0"
        projection={projection}
        insets={insets}
        pitch={20}
        autoRotate={autoRotate}
        values={data?.countries}
        windowWeeks={data?.window.weeks}
        measure={caseBased ? "incidence" : "positivity"}
        layers={layers}
        fill={detection.fill}
        rings={detection.rings}
        hoverDetail={detection.hoverDetail}
        selectedIso3={selected}
        onCountryClick={(c) => {
          setAutoRotate(false);
          setSelected(c.iso3);
        }}
      />

      <h1 className="sr-only">Global {info.label.toLowerCase()} surveillance</h1>
      <button
        type="button"
        onClick={() => setControlsOpen((o) => !o)}
        aria-expanded={controlsOpen}
        aria-controls="map-controls"
        className="absolute left-3 top-3 z-10 flex h-8 items-center gap-1.5 panel-glass rounded-lg px-2.5 text-xs font-medium lg:hidden"
      >
        {controlsOpen ? <X className="size-4" aria-hidden /> : <SlidersHorizontal className="size-4" aria-hidden />}
        {controlsOpen ? "Close" : "Layers"}
      </button>
      <aside
        id="map-controls"
        aria-label="Map controls"
        className={cn(
          "absolute left-3 top-14 max-h-[calc(100%-13rem)] w-64 space-y-4 overflow-y-auto panel-glass p-3 lg:top-3 lg:block lg:max-h-none lg:overflow-visible",
          controlsOpen ? "block" : "hidden",
        )}
      >
        <section className="space-y-2.5">
          <SectionTitle>View</SectionTitle>
          <div className="grid grid-cols-2 gap-1 rounded-full border border-border bg-muted p-1 text-xs" role="radiogroup" aria-label="Projection">
            {(["globe", "mercator"] as const).map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={projection === p}
                onClick={() => setProjection(p)}
                className={cn(
                  "rounded-full px-3 py-1 transition-colors",
                  projection === p ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {p === "globe" ? "3D globe" : "Flat map"}
              </button>
            ))}
          </div>
          <Toggle id="rotate" label="Auto-rotate" checked={autoRotate} onChange={setAutoRotate} />
        </section>

        <section className="space-y-2 border-t border-border pt-3">
          <SectionTitle>Country fill</SectionTitle>
          <div className="space-y-0.5" role="radiogroup" aria-label="Country fill">
            {fillOptions.map((m) => (
              <button
                key={m.key}
                type="button"
                role="radio"
                aria-checked={activeFill === m.key}
                onClick={() => setFillMode(m.key)}
                className={cn(
                  "flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs transition-colors",
                  activeFill === m.key ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <span
                  className={cn(
                    "grid size-3 place-items-center rounded-full border",
                    activeFill === m.key ? "border-primary" : "border-muted-foreground/50",
                  )}
                  aria-hidden
                >
                  {activeFill === m.key && <span className="size-1.5 rounded-full bg-primary" />}
                </span>
                {m.label}
              </button>
            ))}
          </div>
          <div className="pt-1">
            <SectionTitle>Overlays</SectionTitle>
          </div>
          <Toggle
            id="layer-detections"
            label={caseBased ? "Reported cases (3D columns)" : "Detections (3D columns)"}
            checked={detections}
            onChange={setDetections}
            swatch={<span className="h-3 w-1.5 rounded-t-[2px] bg-[#4fcfbd]" />}
          />
          {info.features.detection ? (
            <Toggle
              id="layer-anomalies"
              label="Anomalies (rings)"
              checked={showAnomalies}
              onChange={(v) => {
                setShowAnomalies(v);
                setParam("anomalies", v ? "1" : null);
              }}
              swatch={<span className="size-2.5 rounded-full border-2 border-[#f6f0e3]" />}
            />
          ) : (
            <p className="text-[10.5px] leading-snug text-muted-foreground">
              Anomaly and hot-spot layers for {info.label.toLowerCase()} are planned for a later phase.
            </p>
          )}
        </section>

        <section className="max-h-[34vh] overflow-y-auto border-t border-border pt-3">
          {caseBased ? (
            activeFill === "positivity" ? (
              <IncidenceLegend disease={info.label} showColumns={detections} />
            ) : (
              detections && (
                <p className="text-[11px] text-muted-foreground">Column height ∝ √ weekly average reported cases</p>
              )
            )
          ) : (
            <>
              {fillMode === "positivity" && <PositivityLegend showDetections={detections} />}
              {fillMode !== "positivity" && detections && <PositivityLegend showDetections hideScale className="mb-2" />}
            </>
          )}
          {detection.legend}
          {detection.note && <p className="mt-2 text-[10.5px] leading-snug text-muted-foreground">{detection.note}</p>}
          {detection.error && <QueryError error={detection.error} className="mt-2 text-[11px] text-status-error" />}
          {activeFill === "none" && !detections && !anomaliesOn && (
            <p className="text-[11px] text-muted-foreground">All data layers are hidden.</p>
          )}
        </section>

        {data && (
          <p className="border-t border-border pt-3 text-[11px] text-muted-foreground">
            {windowLabel(data.window)} · {formatInt(data.countries.length)} areas reporting
            {data.region ? ` in ${data.region}` : ""}
          </p>
        )}
      </aside>

      {selected && data && (
        <div className="absolute bottom-[132px] right-3 top-3 flex items-start">
          <CountryPanel
            key={selected}
            iso3={selected}
            disease={filters.disease}
            window={data.window}
            value={valueByIso3.get(selected)}
            onClose={() => setSelected(null)}
          />
        </div>
      )}

      <div ref={setBottomBar} className="absolute inset-x-3 bottom-3 space-y-1.5 lg:left-[284px]">
        {global.error && <QueryError error={global.error} className="rounded-md bg-card/90 p-2 text-xs text-status-error" />}
        {data && (
          <>
            <TimeSlider
              meta={data.meta}
              week={filters.to ?? data.meta.reference_week}
              onChange={(week) => setFilters({ to: week === data.meta.reference_week ? null : week })}
              onPrefetch={prefetch}
            />
            <Provenance meta={data.meta} className="px-1 text-[10px]" />
          </>
        )}
      </div>
    </div>
  );
}
