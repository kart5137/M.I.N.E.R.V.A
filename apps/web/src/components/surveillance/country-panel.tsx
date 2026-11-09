"use client";

import { X } from "lucide-react";
import { useMemo } from "react";

import { QueryError } from "@/components/common/query-state";
import { WeeklyChart, type WeeklyPoint } from "@/components/charts/weekly-chart";
import { useCountryProfile, useCountryTimeseries } from "@/hooks/use-surveillance";
import { addWeeks, formatCompact, formatInt, formatPct, formatWeek, windowLabel } from "@/lib/format";
import { MIN_SPECIMENS } from "@/lib/positivity-scale";
import type { CountryWindowValue, WindowInfo } from "@/lib/types";

const HISTORY_WEEKS = 104;
const NA = <span className="text-muted-foreground">Not available</span>;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 py-1">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="metric text-right">{children}</dd>
    </div>
  );
}

export function CountryPanel({
  iso3,
  window: w,
  value,
  onClose,
}: {
  iso3: string;
  window: WindowInfo;
  value: CountryWindowValue | undefined;
  onClose: () => void;
}) {
  const profile = useCountryProfile(iso3);
  const from = addWeeks(w.end, -(HISTORY_WEEKS - 1));
  const series = useCountryTimeseries(iso3, from, w.end);
  const p = profile.data;

  const points = useMemo<WeeklyPoint[]>(
    () =>
      (series.data?.points ?? []).map((s) => ({
        week: s.week_start,
        value: s.reported ? s.positivity : null,
        provisional: s.is_provisional,
        details: [
          ["Detections", formatInt(s.positives)],
          ["Specimens tested", formatInt(s.specimens_tested)],
        ],
      })),
    [series.data],
  );

  return (
    <aside
      className="flex max-h-full w-80 flex-col overflow-y-auto rounded-lg border border-border bg-card/95 text-xs backdrop-blur"
      aria-label={`${p?.name ?? iso3} details`}
    >
      <header className="flex items-start justify-between gap-2 border-b border-border p-3">
        <div>
          <h2 className="text-sm font-semibold">{p?.name ?? iso3}</h2>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="font-mono">{iso3}</span>
            {p?.who_region && <span>· {p.who_region}</span>}
            {p?.coverage && (
              <span
                className="rounded border border-border px-1 font-medium text-foreground"
                title="Data-coverage tier (A best – D sparse) at the reference week"
              >
                Tier {p.coverage.tier}
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          aria-label="Close country panel"
        >
          <X className="size-4" />
        </button>
      </header>

      {profile.error && <QueryError error={profile.error} />}

      <section className="border-b border-border p-3">
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {windowLabel(w)}
        </h3>
        {value ? (
          <dl className="mt-1.5">
            <Row label="Test positivity">{formatPct(value.positivity)}</Row>
            <Row label="Detections">{formatInt(value.positives)}</Row>
            <Row label="Specimens tested">{formatInt(value.specimens_tested)}</Row>
            <Row label="Weeks reported">
              {value.weeks_reported} of {w.weeks}
            </Row>
          </dl>
        ) : (
          <p className="mt-1.5 text-muted-foreground">No report in this window.</p>
        )}
        {value && (value.specimens_tested ?? 0) < MIN_SPECIMENS && value.positivity != null && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            Fewer than {MIN_SPECIMENS} specimens tested: positivity is unstable.
          </p>
        )}
        {value && value.provisional_weeks > 0 && (
          <p className="mt-1 text-[11px] text-status-warn">Includes provisional weeks; values may change.</p>
        )}
      </section>

      <section className="border-b border-border p-3">
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Test positivity · {HISTORY_WEEKS} weeks
        </h3>
        <div className="mt-2 h-36">
          {series.error ? (
            <QueryError error={series.error} />
          ) : (
            series.data && (
              <WeeklyChart
                compact
                points={points}
                kind="line"
                seriesName="Test positivity"
                formatValue={(v) => formatPct(v)}
                formatAxis={(v) => `${Math.round(v * 100)}%`}
                highlight={{ start: w.start, end: w.end }}
                ariaLabel={`Weekly test positivity in ${p?.name ?? iso3}`}
              />
            )
          )}
        </div>
        <p className="mt-1 text-[10.5px] text-muted-foreground">Gaps are weeks without testing, not zero.</p>
      </section>

      <section className="p-3">
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Context</h3>
        <dl className="mt-1.5">
          <Row label="Population">
            {p?.population ? `${formatCompact(p.population.value)} (${p.population.year})` : p ? NA : "…"}
          </Row>
          <Row label="Reporting since">{p ? formatWeek(p.surveillance.first_week) : "…"}</Row>
          <Row label="Last reported week">{p ? formatWeek(p.surveillance.last_reported_week) : "…"}</Row>
          <Row label="Data completeness">
            {p?.coverage ? formatPct(p.coverage.completeness, 0) : p ? NA : "…"}
          </Row>
          <Row label="Hemisphere">{p?.hemisphere ?? (p ? NA : "…")}</Row>
        </dl>
        {p && !p.has_geometry && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            This area has no separate boundary in Natural Earth, so it is not drawn on the map.
          </p>
        )}
      </section>
    </aside>
  );
}
