"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Clock } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import { QueryError } from "@/components/common/query-state";
import { Provenance } from "@/components/common/provenance";
import { Globe, type GlobeLayers } from "@/components/globe";
import { Switch } from "@/components/ui/switch";
import { globalQueryOptions, useGlobalSurveillance } from "@/hooks/use-surveillance";
import { useFilters } from "@/lib/filters";
import { formatInt, windowLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CountryPanel } from "./country-panel";
import { PositivityLegend } from "./positivity-legend";
import { TimeSlider } from "./time-slider";

/** Layers produced by later milestones; listed (disabled) so users know they are coming. */
const PLANNED_LAYERS = [
  { label: "Anomalies", milestone: "M6" },
  { label: "Hotspots (Gi*)", milestone: "M6" },
  { label: "Forecast change", milestone: "M5" },
  { label: "Risk level", milestone: "M5" },
];

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
  const [autoRotate, setAutoRotate] = useState(!selected);
  const [layers, setLayers] = useState<GlobeLayers>({ positivity: true, detections: true });

  const queryClient = useQueryClient();
  const global = useGlobalSurveillance(filters);
  const data = global.data;
  const valueByIso3 = useMemo(() => new Map(data?.countries.map((c) => [c.iso3, c]) ?? []), [data]);

  const prefetch = useCallback(
    (week: string) => void queryClient.prefetchQuery(globalQueryOptions({ ...filters, to: week })),
    [queryClient, filters],
  );

  return (
    <div className="relative flex-1 overflow-hidden">
      <Globe
        className="absolute inset-0"
        projection={projection}
        pitch={20}
        autoRotate={autoRotate}
        values={data?.countries}
        windowWeeks={data?.window.weeks}
        layers={layers}
        selectedIso3={selected}
        onCountryClick={(c) => {
          setAutoRotate(false);
          setSelected(c.iso3);
        }}
      />

      <aside className="absolute left-3 top-3 w-64 space-y-4 rounded-lg border border-border bg-card/90 p-3 backdrop-blur">
        <section className="space-y-2.5">
          <SectionTitle>View</SectionTitle>
          <div className="grid grid-cols-2 gap-1 rounded-md bg-muted p-0.5 text-xs" role="radiogroup" aria-label="Projection">
            {(["globe", "mercator"] as const).map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={projection === p}
                onClick={() => setProjection(p)}
                className={cn(
                  "rounded px-2 py-1 transition-colors",
                  projection === p ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {p === "globe" ? "3D globe" : "Flat map"}
              </button>
            ))}
          </div>
          <Toggle id="rotate" label="Auto-rotate" checked={autoRotate} onChange={setAutoRotate} />
        </section>

        <section className="space-y-2.5 border-t border-border pt-3">
          <SectionTitle>Layers</SectionTitle>
          <Toggle
            id="layer-positivity"
            label="Test positivity"
            checked={layers.positivity}
            onChange={(v) => setLayers((l) => ({ ...l, positivity: v }))}
            swatch={<span className="size-2.5 rounded-[2px] bg-[#3987e5]" />}
          />
          <Toggle
            id="layer-detections"
            label="Detections (3D columns)"
            checked={layers.detections}
            onChange={(v) => setLayers((l) => ({ ...l, detections: v }))}
            swatch={<span className="h-3 w-1.5 rounded-t-[2px] bg-[#d95926]" />}
          />
          <ul className="space-y-1.5 pt-1">
            {PLANNED_LAYERS.map((l) => (
              <li key={l.label} className="flex items-center justify-between text-xs text-muted-foreground/70">
                <span>{l.label}</span>
                <span className="flex items-center gap-1 rounded bg-muted px-1.5 text-[10.5px]">
                  <Clock className="size-3" aria-hidden />
                  {l.milestone}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="border-t border-border pt-3">
          {layers.positivity || layers.detections ? (
            <PositivityLegend showDetections={layers.detections} />
          ) : (
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
            window={data.window}
            value={valueByIso3.get(selected)}
            onClose={() => setSelected(null)}
          />
        </div>
      )}

      <div className="absolute inset-x-3 bottom-3 space-y-1.5 lg:left-[284px]">
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
