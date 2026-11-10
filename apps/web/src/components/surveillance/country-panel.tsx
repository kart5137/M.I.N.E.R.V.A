"use client";

import { ArrowRight, X } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { QueryError } from "@/components/common/query-state";
import { WeeklyChart, type WeeklyPoint } from "@/components/charts/weekly-chart";
import { useCountryProfile, useCountryTimeseries } from "@/hooks/use-surveillance";
import { DISEASES, type DiseaseKey } from "@/lib/diseases";
import { diseaseParam, withParams } from "@/lib/filters";
import { addWeeks, formatCompact, formatInt, formatPct, formatRate, formatWeek, windowLabel } from "@/lib/format";
import { monthSpan } from "@/lib/incidence-scale";
import { MIN_SPECIMENS } from "@/lib/positivity-scale";
import type { CountryWindowValue, MonthPoint, WindowInfo } from "@/lib/types";

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
  disease,
  window: w,
  value,
  onClose,
}: {
  iso3: string;
  disease: DiseaseKey;
  window: WindowInfo;
  value: CountryWindowValue | undefined;
  onClose: () => void;
}) {
  const caseBased = DISEASES[disease].caseBased;
  const profile = useCountryProfile(iso3, disease);
  const from = addWeeks(w.end, -(HISTORY_WEEKS - 1));
  const series = useCountryTimeseries(iso3, from, w.end, disease);
  const p = profile.data;
  const monthlyOnly =
    caseBased && !!series.data && series.data.points.every((s) => !s.reported) &&
    (series.data.monthly?.length ?? 0) > 0;

  const points = useMemo<WeeklyPoint[]>(
    () =>
      caseBased
        ? (series.data?.points ?? []).map((s) => ({
            week: s.week_start,
            value: s.reported ? (s.cases ?? null) : null,
            provisional: s.is_provisional,
            details: [["Per 100k", formatRate(s.incidence)]],
          }))
        : (series.data?.points ?? []).map((s) => ({
            week: s.week_start,
            value: s.reported ? s.positivity : null,
            provisional: s.is_provisional,
            details: [
              ["Detections", formatInt(s.positives)],
              ["Specimens tested", formatInt(s.specimens_tested)],
            ],
          })),
    [series.data, caseBased],
  );

  return (
    <aside
      className="flex max-h-full w-80 flex-col overflow-y-auto panel-glass text-xs"
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
        {value && caseBased ? (
          <dl className="mt-1.5">
            <Row label="Cases per 100k / week">{formatRate(value.incidence)}</Row>
            <Row label="Reported cases">{formatInt(value.cases)}</Row>
            {value.grain === "month" && value.period_start && value.period_end ? (
              <Row label="Monthly report">{monthSpan(value.period_start, value.period_end)}</Row>
            ) : (
              <Row label="Weeks reported">
                {value.weeks_reported} of {w.weeks}
              </Row>
            )}
          </dl>
        ) : value ? (
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
        {value && caseBased && value.grain === "month" && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            Reports monthly: the value covers the calendar months overlapping this period.
          </p>
        )}
        {value && caseBased && value.incidence == null && (
          <p className="mt-1 text-[11px] text-muted-foreground">No population figure, so no rate.</p>
        )}
        {value && !caseBased && (value.specimens_tested ?? 0) < MIN_SPECIMENS && value.positivity != null && (
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
          {caseBased ? "Reported cases" : "Test positivity"} · {HISTORY_WEEKS} weeks
        </h3>
        {/* The monthly table sizes itself; charts need a fixed height. */}
        <div className={monthlyOnly ? "mt-2" : "mt-2 h-36"}>
          {series.error ? (
            <QueryError error={series.error} />
          ) : monthlyOnly ? (
            <MonthlyList months={series.data!.monthly!} />
          ) : caseBased ? (
            series.data && (
              <WeeklyChart
                compact
                points={points}
                kind="bar"
                seriesName="Reported cases"
                formatValue={(v) => formatInt(v)}
                formatAxis={(v) => formatCompact(v)}
                highlight={{ start: w.start, end: w.end }}
                ariaLabel={`Weekly reported cases in ${p?.name ?? iso3}`}
              />
            )
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
        <p className="mt-1 text-[10.5px] text-muted-foreground">
          {monthlyOnly
            ? "This country reports monthly; latest months shown."
            : caseBased
              ? "Gaps are weeks without a report, not zero."
              : "Gaps are weeks without testing, not zero."}
        </p>
      </section>

      <section className="p-3">
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Context</h3>
        <dl className="mt-1.5">
          <Row label="Population">
            {p?.population ? `${formatCompact(p.population.value)} (${p.population.year})` : p ? NA : "…"}
          </Row>
          <Row label="Reporting since">{p ? formatWeek(p.surveillance.first_week) : "…"}</Row>
          {caseBased && p?.surveillance.last_reported_month ? (
            <Row label="Last monthly report">{monthSpan(p.surveillance.last_reported_month, p.surveillance.last_reported_month)}</Row>
          ) : (
            <Row label="Last reported week">{p ? formatWeek(p.surveillance.last_reported_week) : "…"}</Row>
          )}
          <Row label="Data completeness">
            {p?.coverage ? formatPct(p.coverage.completeness, 0) : p ? NA : "…"}
          </Row>
          {!caseBased && <Row label="Hemisphere">{p?.hemisphere ?? (p ? NA : "…")}</Row>}
        </dl>
        {p && !p.has_geometry && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            This area has no separate boundary in Natural Earth, so it is not drawn on the map.
          </p>
        )}
        <Link
          href={withParams(`/countries/${iso3}`, diseaseParam(disease))}
          className="mt-3 flex items-center justify-center gap-1 rounded-md border border-border py-1.5 text-xs text-foreground hover:bg-accent"
        >
          Open country intelligence
          <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      </section>
    </aside>
  );
}

/** Latest monthly reports, for countries that report monthly only. */
function MonthlyList({ months }: { months: MonthPoint[] }) {
  const latest = months.slice(-6).reverse();
  return (
    <table className="w-full text-[11px]">
      <thead className="text-muted-foreground">
        <tr>
          <th className="py-1 text-left font-normal">Month</th>
          <th className="py-1 text-right font-normal">Cases</th>
          <th className="py-1 text-right font-normal">Per 100k / wk</th>
        </tr>
      </thead>
      <tbody className="metric">
        {latest.map((m) => (
          <tr key={m.month_start} className="border-t border-border/60">
            <td className="py-1">
              {monthSpan(m.month_start, m.month_start)}
              {m.is_provisional && <span className="ml-1 text-status-warn">provisional</span>}
            </td>
            <td className="py-1 text-right">{formatInt(m.cases)}</td>
            <td className="py-1 text-right">{formatRate(m.incidence)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
