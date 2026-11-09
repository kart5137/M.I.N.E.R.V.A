"use client";

import { MapboxOverlay } from "@deck.gl/mapbox";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { FeatureCollection, MultiPolygon, Polygon } from "geojson";
import {
  Map as MapLibreMap,
  type MapGeoJSONFeature,
  setWorkerUrl,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

export type CountryProps = {
  iso3: string;
  name: string;
  who_region: string | null;
  label: [number, number];
};
type Countries = FeatureCollection<Polygon | MultiPolygon, CountryProps>;

export interface GlobeProps {
  projection?: "globe" | "mercator";
  autoRotate?: boolean;
  showCentroids?: boolean;
  interactive?: boolean;
  className?: string;
  onCountryClick?: (country: CountryProps) => void;
}

/** Country boundaries: Natural Earth 1:50m (public domain), served from PostGIS. */
const COUNTRIES_URL = `${API_BASE_URL}/geo/countries`;
const ROTATE_DEG_PER_SEC = 4;

// Served by scripts/copy-maplibre-worker.mjs (runs before dev/build).
setWorkerUrl("/vendor/maplibre-gl-worker.mjs");

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
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

export function Globe({
  projection = "globe",
  autoRotate = true,
  showCentroids = false,
  interactive = true,
  className,
  onCountryClick,
}: GlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const rotatingRef = useRef(autoRotate);
  const clickRef = useRef(onCountryClick);
  const [countries, setCountries] = useState<Countries | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; country: CountryProps } | null>(null);

  useEffect(() => {
    clickRef.current = onCountryClick;
  }, [onCountryClick]);

  // Re-enable or disable rotation when the prop changes (user interaction also stops it).
  useEffect(() => {
    rotatingRef.current = autoRotate;
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

    map.on("load", () => {
      map.addSource("countries", { type: "geojson", data: countries, promoteId: "iso3" });
      map.addLayer({
        id: "country-fill",
        type: "fill",
        source: "countries",
        paint: {
          "fill-color": [
            "case",
            ["boolean", ["feature-state", "hover"], false],
            "#1d3a5c",
            token("--globe-land") || "#15203a",
          ],
        },
      });
      map.addLayer({
        id: "country-line",
        type: "line",
        source: "countries",
        paint: {
          "line-color": [
            "case",
            ["boolean", ["feature-state", "hover"], false],
            token("--globe-hover") || "#22d3ee",
            token("--globe-border") || "#2b3a5a",
          ],
          "line-width": ["case", ["boolean", ["feature-state", "hover"], false], 1.2, 0.5],
        },
      });
    });

    const clearHover = () => {
      if (hoveredId !== null) map.setFeatureState({ source: "countries", id: hoveredId }, { hover: false });
      hoveredId = null;
      setHover(null);
      map.getCanvas().style.cursor = "";
    };

    map.on("mousemove", "country-fill", (e) => {
      const f = e.features?.[0] as MapGeoJSONFeature | undefined;
      if (!f) return;
      const id = String(f.id);
      if (hoveredId !== id) {
        if (hoveredId !== null) map.setFeatureState({ source: "countries", id: hoveredId }, { hover: false });
        map.setFeatureState({ source: "countries", id }, { hover: true });
        hoveredId = id;
      }
      map.getCanvas().style.cursor = "pointer";
      setHover({ x: e.point.x, y: e.point.y, country: f.properties as CountryProps });
    });
    map.on("mouseleave", "country-fill", clearHover);
    // MapLibre stringifies nested properties (e.g. `label`) in events, so resolve the
    // clicked country from the source data instead of the event payload.
    const byIso3 = new Map(countries.features.map((f) => [f.properties.iso3, f.properties]));
    map.on("click", "country-fill", (e) => {
      const props = byIso3.get(String(e.features?.[0]?.id));
      if (props) clickRef.current?.(props);
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
    if (!map) return;
    const apply = () => map.setProjection({ type: projection });
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [projection]);

  // deck.gl layers
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !countries) return;
    overlay.setProps({
      layers: showCentroids
        ? [
            new ScatterplotLayer<CountryProps>({
              id: "country-centroids",
              data: countries.features.map((f) => f.properties),
              getPosition: (d) => d.label,
              getRadius: 45_000,
              radiusMinPixels: 1.5,
              radiusMaxPixels: 5,
              getFillColor: [34, 211, 238, 200],
            }),
          ]
        : [],
    });
  }, [showCentroids, countries]);

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
      {hover && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border border-border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <div className="font-medium text-foreground">{hover.country.name}</div>
          <div className="font-mono text-[10.5px] text-muted-foreground">{hover.country.iso3}</div>
        </div>
      )}
      <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] text-muted-foreground/60">
        Boundaries: Natural Earth
      </div>
    </div>
  );
}
