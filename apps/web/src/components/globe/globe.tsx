"use client";

import { MapboxOverlay } from "@deck.gl/mapbox";
import { ColumnLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { FeatureCollection, MultiPolygon, Polygon } from "geojson";
import {
  type ExpressionSpecification,
  Map as MapLibreMap,
  setWorkerUrl,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import { formatInt, formatPct } from "@/lib/format";
import {
  DETECTIONS_RGB,
  FEW_SPECIMENS_COLOR,
  MIN_SPECIMENS,
  POSITIVITY_BINS,
  positivityClass,
} from "@/lib/positivity-scale";
import type { CountryWindowValue } from "@/lib/types";
import { cn } from "@/lib/utils";

export type CountryProps = {
  iso3: string;
  name: string;
  who_region: string | null;
  label: [number, number];
};
type Countries = FeatureCollection<Polygon | MultiPolygon, CountryProps>;

export interface GlobeLayers {
  positivity: boolean;
  detections: boolean;
}

/** A categorical fill that replaces the positivity choropleth (detection layers). */
export interface GlobeFill {
  /** Class index per country; countries without one keep the land colour ("no data"). */
  byIso3: Map<string, number>;
  colors: string[];
}

/** Outline ring drawn at a country's label point (e.g. anomalies). */
export interface GlobeRing {
  iso3: string;
  /** Radius in metres. */
  radius: number;
}

export interface GlobeProps {
  projection?: "globe" | "mercator";
  /** Initial camera tilt in degrees (makes 3D columns readable). */
  pitch?: number;
  autoRotate?: boolean;
  interactive?: boolean;
  className?: string;
  /** Per-country values for the current window (from /surveillance/global). */
  values?: CountryWindowValue[];
  /** Window length, used to show detections as a weekly average. */
  windowWeeks?: number;
  layers?: GlobeLayers;
  selectedIso3?: string | null;
  onCountryClick?: (country: CountryProps) => void;
  /** When set, replaces the positivity fill. */
  fill?: GlobeFill | null;
  rings?: GlobeRing[];
  ringColor?: [number, number, number];
  /** Extra lines for the hover card (layer-specific values). */
  hoverDetail?: (iso3: string) => React.ReactNode;
}

/** Country boundaries: Natural Earth 1:50m (public domain), served from PostGIS. */
const COUNTRIES_URL = `${API_BASE_URL}/geo/countries`;
const ROTATE_DEG_PER_SEC = 4;
/** Column height (m) per √(weekly average detections). Fixed, so heights compare over time. */
const METRES_PER_SQRT_DETECTION = 12_000;
const DEFAULT_LAYERS: GlobeLayers = { positivity: true, detections: false };
const DEFAULT_RING: [number, number, number] = [241, 245, 249];

// Served by scripts/copy-maplibre-worker.mjs (runs before dev/build).
setWorkerUrl("/vendor/maplibre-gl-worker.mjs");

function token(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function buildStyle(projection: "globe" | "mercator"): StyleSpecification {
  return {
    version: 8,
    projection: { type: projection },
    sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.85, 5, 0.4, 7, 0] },
    sources: {},
    layers: [{ id: "ocean", type: "background", paint: { "background-color": "#0a1120" } }],
  };
}

function classColor(colors: string[]): ExpressionSpecification {
  const land = token("--globe-land", "#15203a");
  return [
    "match",
    ["coalesce", ["feature-state", "cls"], -1],
    ...colors.flatMap((c, i) => [i, c]),
    land,
  ] as unknown as ExpressionSpecification;
}

function fillColor(showPositivity: boolean): ExpressionSpecification | string {
  const land = token("--globe-land", "#15203a");
  if (!showPositivity) return land;
  const bins = POSITIVITY_BINS.flatMap((b, i) => [i + 1, b.color]);
  return [
    "match",
    ["coalesce", ["feature-state", "cls"], -1],
    0,
    FEW_SPECIMENS_COLOR,
    ...bins,
    land,
  ] as ExpressionSpecification;
}

export function Globe({
  projection = "globe",
  pitch = 0,
  autoRotate = true,
  interactive = true,
  className,
  values,
  windowWeeks = 1,
  layers = DEFAULT_LAYERS,
  selectedIso3 = null,
  onCountryClick,
  fill = null,
  rings,
  ringColor = DEFAULT_RING,
  hoverDetail,
}: GlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const rotatingRef = useRef(autoRotate);
  const clickRef = useRef(onCountryClick);
  const [countries, setCountries] = useState<Countries | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [styleReady, setStyleReady] = useState(false);
  const [hover, setHover] = useState<{ x: number; y: number; iso3: string } | null>(null);

  const byIso3 = useMemo(
    () => new Map(countries?.features.map((f) => [f.properties.iso3, f.properties]) ?? []),
    [countries],
  );
  const valueByIso3 = useMemo(() => new Map(values?.map((v) => [v.iso3, v]) ?? []), [values]);

  useEffect(() => {
    clickRef.current = onCountryClick;
  }, [onCountryClick]);

  useEffect(() => {
    // Respect the system "reduce motion" setting: no idle rotation.
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    rotatingRef.current = autoRotate && !reduce;
  }, [autoRotate]);

  // Boundaries
  useEffect(() => {
    let cancelled = false;
    fetch(COUNTRIES_URL)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: Countries) => !cancelled && setCountries(d))
      .catch((e: Error) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  // Map lifecycle
  useEffect(() => {
    if (!containerRef.current || !countries) return;

    const map = new MapLibreMap({
      container: containerRef.current,
      style: buildStyle(projection),
      center: [15, 20],
      zoom: 1.35,
      pitch,
      minZoom: 0.8,
      maxZoom: 6,
      interactive,
      attributionControl: false,
      renderWorldCopies: false,
    });
    mapRef.current = map;

    // M1 spike result: deck.gl 9.4 interleaved mode renders nothing on MapLibre 6
    // (no error). Overlaid mode (separate canvas, deck GlobeView synced to the map) works
    // for globe and mercator; deck layers therefore always draw above map layers.
    const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay);

    let hoveredId: string | null = null;
    const accent = token("--globe-hover", "#22d3ee");
    const active: ExpressionSpecification = [
      "any",
      ["boolean", ["feature-state", "hover"], false],
      ["boolean", ["feature-state", "selected"], false],
    ];

    map.on("load", () => {
      map.addSource("countries", { type: "geojson", data: countries, promoteId: "iso3" });
      map.addLayer({
        id: "country-fill",
        type: "fill",
        source: "countries",
        paint: { "fill-color": token("--globe-land", "#15203a") },
      });
      map.addLayer({
        id: "country-line",
        type: "line",
        source: "countries",
        paint: {
          "line-color": ["case", active, accent, token("--globe-border", "#2b3a5a")],
          "line-width": ["case", active, 1.6, 0.5],
        },
      });
      setStyleReady(true);
    });

    const clearHover = () => {
      if (hoveredId !== null) map.setFeatureState({ source: "countries", id: hoveredId }, { hover: false });
      hoveredId = null;
      setHover(null);
      map.getCanvas().style.cursor = "";
    };

    map.on("mousemove", "country-fill", (e) => {
      const id = e.features?.[0]?.id;
      if (id == null) return;
      const iso3 = String(id);
      if (hoveredId !== iso3) {
        if (hoveredId !== null) map.setFeatureState({ source: "countries", id: hoveredId }, { hover: false });
        map.setFeatureState({ source: "countries", id: iso3 }, { hover: true });
        hoveredId = iso3;
      }
      map.getCanvas().style.cursor = "pointer";
      setHover({ x: e.point.x, y: e.point.y, iso3 });
    });
    map.on("mouseleave", "country-fill", clearHover);
    // MapLibre stringifies nested properties (e.g. `label`) in events, so resolve the
    // clicked country from the source data instead of the event payload.
    const props = new Map(countries.features.map((f) => [f.properties.iso3, f.properties]));
    map.on("click", "country-fill", (e) => {
      const p = props.get(String(e.features?.[0]?.id));
      if (p) clickRef.current?.(p);
    });

    // Slow auto-rotation that stops for good once the user interacts.
    let frame = 0;
    let last = performance.now();
    const stop = () => {
      rotatingRef.current = false;
    };
    map.on("mousedown", stop);
    map.on("touchstart", stop);
    map.on("wheel", stop);
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      if (rotatingRef.current && !map.isMoving()) {
        const c = map.getCenter();
        map.jumpTo({ center: [c.lng + ROTATE_DEG_PER_SEC * dt, c.lat] });
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      setStyleReady(false);
      overlayRef.current = null;
      mapRef.current = null;
      map.remove();
    };
    // Projection changes are applied in place below; recreate only on data/interactivity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countries, interactive]);

  // Projection toggle
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReady) return;
    map.setProjection({ type: projection });
  }, [projection, styleReady]);

  // Choropleth: class per country in feature state, colour by expression. A detection
  // fill (`fill`) replaces the positivity classes while it is set.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReady || !countries) return;
    for (const f of countries.features) {
      const iso3 = f.properties.iso3;
      const cls = fill ? (fill.byIso3.get(iso3) ?? -1) : positivityClass(valueByIso3.get(iso3));
      map.setFeatureState({ source: "countries", id: iso3 }, { cls });
    }
    map.setPaintProperty(
      "country-fill",
      "fill-color",
      fill ? classColor(fill.colors) : fillColor(layers.positivity),
    );
  }, [valueByIso3, layers.positivity, fill, styleReady, countries]);

  // Selection outline
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReady || !selectedIso3) return;
    map.setFeatureState({ source: "countries", id: selectedIso3 }, { selected: true });
    return () => {
      if (map.getSource("countries")) {
        map.setFeatureState({ source: "countries", id: selectedIso3 }, { selected: false });
      }
    };
  }, [selectedIso3, styleReady]);

  // Detections columns (deck.gl)
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !styleReady) return;
    const data = layers.detections
      ? (values ?? []).flatMap((v) => {
          const c = byIso3.get(v.iso3);
          return c && v.positives ? [{ position: c.label, weekly: v.positives / windowWeeks }] : [];
        })
      : [];
    const ringData = (rings ?? []).flatMap((r) => {
      const c = byIso3.get(r.iso3);
      return c ? [{ position: c.label, radius: r.radius }] : [];
    });
    overlay.setProps({
      layers: [
        new ScatterplotLayer<{ position: [number, number]; radius: number }>({
          id: "rings",
          data: ringData,
          stroked: true,
          filled: false,
          getPosition: (d) => d.position,
          getRadius: (d) => d.radius,
          getLineColor: [...ringColor, 235],
          lineWidthUnits: "pixels",
          getLineWidth: 2,
          radiusUnits: "meters",
        }),
        new ColumnLayer<{ position: [number, number]; weekly: number }>({
          id: "detections",
          data,
          diskResolution: 12,
          radius: 70_000,
          extruded: true,
          getPosition: (d) => d.position,
          getElevation: (d) => Math.sqrt(d.weekly) * METRES_PER_SQRT_DETECTION,
          getFillColor: [...DETECTIONS_RGB, 225],
          material: false,
        }),
      ],
    });
  }, [layers.detections, values, windowWeeks, byIso3, styleReady, rings, ringColor]);

  const hovered = hover ? byIso3.get(hover.iso3) : undefined;
  const hoveredValue = hover ? valueByIso3.get(hover.iso3) : undefined;

  return (
    <div
      className={cn("relative overflow-hidden", className)}
      style={{ background: "radial-gradient(ellipse at center, #0b1426 0%, var(--globe-space) 70%)" }}
    >
      {/* Inline style: maplibre-gl.css sets `.maplibregl-map { position: relative }`
          unlayered, which overrides Tailwind's layered `absolute inset-0`. */}
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
      {!countries && !loadError && (
        <div className="absolute inset-0 grid place-items-center text-xs text-muted-foreground">
          Loading boundaries…
        </div>
      )}
      {loadError && (
        <div className="absolute inset-0 grid place-items-center text-xs text-destructive">
          Could not load country boundaries ({loadError}).
        </div>
      )}
      {hover && hovered && (
        <div
          className="pointer-events-none absolute z-10 min-w-40 rounded-md border border-border bg-popover/95 px-2.5 py-2 text-xs shadow-lg"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-medium text-foreground">{hovered.name}</span>
            <span className="font-mono text-[10.5px] text-muted-foreground">{hovered.iso3}</span>
          </div>
          {values && !fill && <HoverValues v={hoveredValue} />}
          {hoverDetail?.(hover.iso3)}
        </div>
      )}
      <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] text-subtle-foreground">
        Boundaries: Natural Earth
      </div>
    </div>
  );
}

function HoverValues({ v }: { v: CountryWindowValue | undefined }) {
  if (!v) return <div className="mt-1 text-muted-foreground">No report in this window</div>;
  const rows: [string, string][] = [
    ["Positivity", formatPct(v.positivity)],
    ["Detections", formatInt(v.positives)],
    ["Specimens tested", formatInt(v.specimens_tested)],
  ];
  return (
    <div className="mt-1.5 space-y-0.5">
      {rows.map(([k, val]) => (
        <div key={k} className="flex justify-between gap-4">
          <span className="text-muted-foreground">{k}</span>
          <span className="metric text-foreground">{val}</span>
        </div>
      ))}
      {(v.specimens_tested ?? 0) < MIN_SPECIMENS && v.positivity != null && (
        <div className="pt-1 text-[10.5px] text-muted-foreground">Fewer than {MIN_SPECIMENS} specimens: rate unstable</div>
      )}
      {v.provisional_weeks > 0 && (
        <div className="pt-1 text-[10.5px] text-status-warn">Includes provisional weeks</div>
      )}
    </div>
  );
}
