"use client";

import { useState } from "react";

import { type CountryProps, Globe } from "@/components/globe";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

function Toggle({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label htmlFor={id} className="flex items-center justify-between gap-6 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </label>
  );
}

export function SurveillanceView() {
  const [projection, setProjection] = useState<"globe" | "mercator">("globe");
  const [autoRotate, setAutoRotate] = useState(true);
  const [showCentroids, setShowCentroids] = useState(false);
  const [selected, setSelected] = useState<CountryProps | null>(null);

  return (
    <div className="relative flex-1">
      <Globe
        className="absolute inset-0"
        projection={projection}
        autoRotate={autoRotate}
        showCentroids={showCentroids}
        onCountryClick={setSelected}
      />

      <aside className="absolute left-3 top-3 w-60 space-y-3 rounded-lg border border-border bg-card/90 p-3 backdrop-blur">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          View
        </h2>
        <div className="grid grid-cols-2 gap-1 rounded-md bg-muted p-0.5 text-xs" role="radiogroup">
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
        <Toggle id="centroids" label="Country centroids" checked={showCentroids} onChange={setShowCentroids} />
        <p className="border-t border-border pt-2 text-[11px] leading-relaxed text-muted-foreground">
          Surveillance layers (positivity, detections, anomalies, hotspots, risk) are added in
          milestones M3–M6.
        </p>
      </aside>

      {selected && (
        <aside className="absolute right-3 top-3 w-64 rounded-lg border border-border bg-card/90 p-3 backdrop-blur">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">{selected.name}</div>
              <div className="font-mono text-[11px] text-muted-foreground">{selected.iso3}</div>
            </div>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="text-xs text-muted-foreground hover:text-foreground"
              aria-label="Close country panel"
            >
              ✕
            </button>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Country surveillance data will appear here once FluNet is loaded (M2–M3).
          </p>
        </aside>
      )}
    </div>
  );
}
