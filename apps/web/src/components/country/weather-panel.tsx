"use client";

/**
 * Weather at the country's representative point (phase D3): weekly temperature, rainfall
 * and humidity against their 2013–2022 normals. Context only — not a cause of cases.
 */

import { CloudSun } from "lucide-react";
import { useMemo, useState } from "react";

import { WeatherChart, type WeatherPoint } from "@/components/charts/weather-chart";
import { QueryError } from "@/components/common/query-state";
import { useCountryWeather } from "@/hooks/use-surveillance";
import { formatWeek } from "@/lib/format";
import type { CountryWeather, WeatherWeek } from "@/lib/types";
import { cn } from "@/lib/utils";

const RANGES = [
  { key: "1y", label: "1 year", weeks: 52 },
  { key: "2y", label: "2 years", weeks: 104 },
  { key: "5y", label: "5 years", weeks: 260 },
] as const;

const MEASURES = [
  {
    key: "temperature",
    title: "Temperature",
    unit: "°C",
    digits: 1,
    kind: "line",
    note: "weekly mean",
  },
  {
    key: "precipitation",
    title: "Rainfall",
    unit: "mm",
    digits: 0,
    kind: "bar",
    note: "weekly total",
  },
  {
    key: "humidity",
    title: "Relative humidity",
    unit: "%",
    digits: 0,
    kind: "line",
    note: "weekly mean",
  },
] as const;

function pointText(w: CountryWeather): string {
  if (!w.point) return "";
  const { lat, lon, basis } = w.point;
  const where = `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? "E" : "W"}`;
  return `${where} (${basis === "main_town" ? "main town" : "map label point"})`;
}

export function WeatherPanel({ iso3 }: { iso3: string }) {
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("2y");
  const weeks = RANGES.find((r) => r.key === range)!.weeks;
  const q = useCountryWeather(iso3, weeks);
  const w = q.data;

  const series = useMemo(() => {
    const rows = w?.weeks ?? [];
    const pick = (k: (typeof MEASURES)[number]["key"]): WeatherPoint[] =>
      rows.map((r: WeatherWeek) => ({
        week: r.week_start,
        value: r[k],
        normal: r[`${k}_normal` as const],
      }));
    return Object.fromEntries(MEASURES.map((m) => [m.key, pick(m.key)])) as Record<
      (typeof MEASURES)[number]["key"],
      WeatherPoint[]
    >;
  }, [w]);

  // History is loaded over several days within the free API quota (see the backfill job).
  const loading = !!w && (w.loading || !w.point);
  const ready = !!w && !loading && w.weeks.length > 0;

  return (
    <section className="panel p-4" aria-labelledby="weather-title">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-2.5">
          <CloudSun className="mt-0.5 size-4 shrink-0 text-teal" aria-hidden />
          <div>
            <h2 id="weather-title" className="text-sm font-medium">
              Weather
            </h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {!w ? (
                "Loading…"
              ) : loading ? (
                "Weather history is still being loaded"
              ) : (
                <>
                  One point: {pointText(w)} · to week of {formatWeek(w.latest_week)}
                </>
              )}
            </p>
          </div>
        </div>
        {ready && (
          <div
            className="grid grid-cols-3 gap-1 rounded-full border border-border bg-muted p-1 text-xs"
            role="radiogroup"
            aria-label="Weather range"
          >
            {RANGES.map((r) => (
              <button
                key={r.key}
                type="button"
                role="radio"
                aria-checked={range === r.key}
                onClick={() => setRange(r.key)}
                className={cn(
                  "rounded-full px-3 py-1 transition-colors",
                  range === r.key
                    ? "bg-primary font-medium text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}
      </header>

      {q.error && (
        <div className="mt-3">
          <QueryError error={q.error} />
        </div>
      )}

      {loading && (
        <p className="mt-3 text-xs text-muted-foreground">
          {w?.latest_week ? `Loaded to the week of ${formatWeek(w.latest_week)} so far. ` : ""}
          Daily weather since 2013 is fetched from a free service within its daily limit, so the full history for every
          country arrives over about a week. Forecast-ready countries are loaded first.
        </p>
      )}

      {ready && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground" aria-hidden>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded bg-teal" /> Observed
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="w-4 border-t-[1.5px] border-dashed border-muted-foreground" />
              Normal: average of the same week, {w.baseline_years[0]}–{w.baseline_years[1]}
            </span>
          </div>
          <div className="mt-2 grid gap-4 lg:grid-cols-3">
            {MEASURES.map((m) => (
              <div key={m.key}>
                <h3 className="text-[11px] text-muted-foreground">
                  <span className="text-foreground">{m.title}</span> · {m.unit}, {m.note}
                </h3>
                <div className="h-32">
                  <WeatherChart
                    points={series[m.key]}
                    kind={m.kind}
                    name={m.title}
                    unit={m.unit}
                    digits={m.digits}
                    zeroBased={m.key !== "temperature"}
                    max={m.key === "humidity" ? 100 : undefined}
                    ariaLabel={`Weekly ${m.title.toLowerCase()} in ${m.unit} with normal`}
                  />
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {ready && w.source && (
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
          A single point does not represent large or climatically varied countries. Dengue tends to follow warm, wet
          weather with a delay of weeks to months; this panel shows the weather, not a cause of the cases above. ERA5
          grid cells are about 25 km across. {w.source.attribution}
        </p>
      )}
    </section>
  );
}
