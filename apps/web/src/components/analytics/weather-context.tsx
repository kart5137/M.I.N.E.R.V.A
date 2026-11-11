"use client";

/**
 * Dengue Analytics: one country's weekly incidence with its rainfall and temperature for
 * the same weeks, as three aligned charts (one measure per chart, never two y-axes).
 * Context only: the D4 backtest found weather did not clearly improve forecasts
 * (docs/models/dengue-incidence.md).
 */

import { useMemo } from "react";

import { WeatherChart, type WeatherPoint } from "@/components/charts/weather-chart";
import { WeeklyChart, type WeeklyPoint } from "@/components/charts/weekly-chart";
import { QueryError } from "@/components/common/query-state";
import { useCountryTimeseries, useCountryWeatherRange } from "@/hooks/use-surveillance";
import { addWeeks, formatRate } from "@/lib/format";

const WEEKS = 156;

export function WeatherContext({ iso3, name, latestWeek }: { iso3: string; name: string; latestWeek: string }) {
  const from = addWeeks(latestWeek, -(WEEKS - 1));
  const cases = useCountryTimeseries(iso3, from, latestWeek, "dengue");
  const weather = useCountryWeatherRange(iso3, from, latestWeek);

  const { incidence, rain, temp } = useMemo(() => {
    const pts = cases.data?.points ?? [];
    const byWeek = new Map((weather.data?.weeks ?? []).map((w) => [w.week_start, w]));
    // One week axis for all three charts: the case series' weeks (gaps stay gaps).
    const incidence: WeeklyPoint[] = pts.map((p) => ({
      week: p.week_start,
      value: p.reported ? (p.incidence ?? null) : null,
      provisional: p.is_provisional,
    }));
    const w = (k: "precipitation" | "temperature"): WeatherPoint[] =>
      pts.flatMap((p) => {
        const r = byWeek.get(p.week_start);
        return r ? [{ week: p.week_start, value: r[k], normal: r[`${k}_normal` as const] }] : [];
      });
    return { incidence, rain: w("precipitation"), temp: w("temperature") };
  }, [cases.data, weather.data]);

  const hasCases = incidence.some((p) => p.value != null);
  const noWeather = weather.data && weather.data.weeks.length === 0;

  return (
    <div className="space-y-3">
      {cases.error && <QueryError error={cases.error} />}
      {weather.error && <QueryError error={weather.error} />}
      {cases.data && !hasCases && (
        <p className="text-xs text-muted-foreground">{name} has no weekly dengue reports in the last 3 years.</p>
      )}
      {hasCases && (
        <>
          <div>
            <h3 className="text-xs font-medium">Dengue cases per 100,000 per week</h3>
            <div className="h-36">
              <WeeklyChart
                points={incidence}
                kind="line"
                seriesName="Per 100k / week"
                formatValue={(v) => formatRate(v)}
                formatAxis={(v) => formatRate(v)}
                ariaLabel={`Weekly dengue cases per 100,000 in ${name}`}
                compact
              />
            </div>
          </div>
          {noWeather ? (
            <p className="text-xs text-muted-foreground">No weather is stored for {name}.</p>
          ) : (
            <>
              <div>
                <h3 className="text-xs font-medium">Rainfall (weekly total; dashed line = 2013–2022 normal)</h3>
                <div className="h-28">
                  <WeatherChart
                    points={rain}
                    kind="bar"
                    name="Rainfall"
                    unit="mm"
                    digits={0}
                    zeroBased
                    ariaLabel={`Weekly rainfall in ${name}`}
                  />
                </div>
              </div>
              <div>
                <h3 className="text-xs font-medium">Temperature (weekly mean; dashed line = normal)</h3>
                <div className="h-28">
                  <WeatherChart
                    points={temp}
                    kind="line"
                    name="Temperature"
                    unit="°C"
                    digits={1}
                    ariaLabel={`Weekly mean temperature in ${name}`}
                  />
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
