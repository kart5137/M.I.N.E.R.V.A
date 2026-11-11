"use client";

import { AnnualCountryView } from "@/components/annual/annual-country";
import { ArrowLeft, Globe2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { WeeklyChart, type WeeklyPoint } from "@/components/charts/weekly-chart";
import { Provenance } from "@/components/common/provenance";
import { QueryError } from "@/components/common/query-state";
import { SEASON_LABEL, TierBadge } from "@/components/countries/countries-table";
import { useCountryProfile, useCountrySeasons, useCountryTimeseries } from "@/hooks/use-surveillance";
import { ApiError } from "@/lib/api";
import { DISEASES, type DiseaseInfo } from "@/lib/diseases";
import { REGIONS, diseaseParam, useFilters, withParams } from "@/lib/filters";
import { addWeeks, formatCompact, formatInt, formatPct, formatWeek, windowLabel } from "@/lib/format";
import { MIN_SPECIMENS } from "@/lib/positivity-scale";
import type { CountryProfile, HealthValue, ThresholdLevels } from "@/lib/types";
import { cn } from "@/lib/utils";

import { AlertListCard } from "@/components/intelligence/alert-list-card";
import { GenerateReportForm } from "@/components/intelligence/reports-view";

import { CaseCoverage, CaseHistory, CaseRecentStats, hasCaseReports } from "./case-sections";
import { WeatherPanel } from "./weather-panel";
import { ChannelCard } from "./channel-card";
import { AnomalyTimeline, HotspotCard, RiskCard } from "./detection-cards";
import { ForecastSummary } from "./forecast-summary";
import { SeasonChart, SeasonTable } from "./season-chart";

const RANGES = [
  { key: "2y", label: "2 years", weeks: 104 },
  { key: "5y", label: "5 years", weeks: 260 },
  { key: "10y", label: "10 years", weeks: 520 },
  { key: "all", label: "All", weeks: null },
] as const;
/** Indicator values older than this many years are marked as dated. */
const STALE_YEARS = 5;
/** Mirrors pipeline/src/ei_pipeline/quality/coverage.py TIERS (5-year window). */
const TIER_RULES = {
  A: "forecast-ready: ≥ 85% of weeks reported, longest gap ≤ 8 weeks, median ≥ 30 specimens/week, last report ≤ 8 weeks old",
  B: "forecast with caution: ≥ 60% of weeks reported, median ≥ 10 specimens/week, last report ≤ 26 weeks old",
  C: "map and trends only: some data in the 5-year window",
  D: "historical only: no data in the 5-year window",
} as const;

function Card({ title, subtitle, children, className, actions }: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}) {
  return (
    <section className={cn("panel p-4", className)}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>}
        </div>
        {actions}
      </header>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="panel p-3.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tracking-tight">{value}</div>
      {note && <div className="mt-0.5 text-[11px] text-muted-foreground">{note}</div>}
    </div>
  );
}

export function CountryIntelligence() {
  const { iso3: raw } = useParams<{ iso3: string }>();
  const [filters] = useFilters();
  return DISEASES[filters.disease].grain === "year" ? <AnnualCountryView iso3={raw} /> : <WeeklyCountry iso3={raw.toUpperCase()} />;
}

function WeeklyCountry({ iso3 }: { iso3: string }) {
  const [filters] = useFilters();
  const info = DISEASES[filters.disease];
  const profile = useCountryProfile(iso3, info.key);
  const p = profile.data;

  if (profile.error) {
    const notFound = profile.error instanceof ApiError && profile.error.status === 404;
    return (
      <div className="p-6">
        <BackLink />
        <h1 className="mt-4 text-lg font-semibold tracking-tight">{notFound ? "Country not found" : iso3}</h1>
        {notFound ? (
          <p className="mt-1 text-sm text-muted-foreground">No country or area with code “{iso3}”.</p>
        ) : (
          <QueryError error={profile.error} />
        )}
      </div>
    );
  }

  if (info.caseBased) {
    return (
      <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
        <BackLink info={info} />
        <Header iso3={iso3} p={p} info={info} />
        {p && <CaseRecentStats p={p} />}
        {p && !hasCaseReports(p) && (
          <p className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
            <TriangleAlert className="size-4 shrink-0" aria-hidden />
            This area has no {info.label.toLowerCase()} cases reported to WHO. Context indicators are shown where available.
          </p>
        )}
        {p && hasCaseReports(p) && <CaseHistory iso3={iso3} p={p} info={info} />}
        {p && p.surveillance.weeks_reported > 0 && <ChannelCard iso3={iso3} />}
        <div className="grid gap-4 md:grid-cols-3">
          <ForecastSummary iso3={iso3} />
          <RiskCard iso3={iso3} />
          <HotspotCard iso3={iso3} />
        </div>
        {p && p.surveillance.weeks_reported > 0 && <AnomalyTimeline iso3={iso3} />}
        {p && hasCaseReports(p) && <WeatherPanel iso3={iso3} />}
        {p && hasCaseReports(p) && (
          <AlertListCard iso3={iso3} limit={5}>
            <h3 className="mb-2 text-xs font-medium">Country report</h3>
            <GenerateReportForm fixedIso3={iso3} />
          </AlertListCard>
        )}
        {p && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Context p={p} />
            <CaseCoverage p={p} />
          </div>
        )}
        {p && <Provenance meta={p.meta} />}
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <BackLink info={info} />
      <Header iso3={iso3} p={p} info={info} />
      {p && <RecentStats p={p} />}
      {p && p.surveillance.weeks_reported === 0 && (
        <p className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
          <TriangleAlert className="size-4 shrink-0" aria-hidden />
          This area has no influenza testing reported to WHO FluNet. Context indicators are shown where available.
        </p>
      )}
      {p && p.surveillance.weeks_reported > 0 && (
        <>
          <History iso3={iso3} />
          <Seasons iso3={iso3} />
        </>
      )}
      <div className="grid gap-4 md:grid-cols-3">
        <ForecastSummary iso3={iso3} />
        <RiskCard iso3={iso3} />
        <HotspotCard iso3={iso3} />
      </div>
      {p && p.surveillance.weeks_reported > 0 && <AnomalyTimeline iso3={iso3} />}
      {p && p.surveillance.weeks_reported > 0 && (
        <AlertListCard iso3={iso3} limit={5}>
          <h3 className="mb-2 text-xs font-medium">Country report</h3>
          <GenerateReportForm fixedIso3={iso3} />
        </AlertListCard>
      )}
      {p && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Context p={p} />
          <Coverage p={p} />
        </div>
      )}
      {p && <Provenance meta={p.meta} />}
    </div>
  );
}

function BackLink({ info }: { info?: DiseaseInfo }) {
  return (
    <Link href={withParams("/countries", info ? diseaseParam(info.key) : "")} className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-3.5" aria-hidden />
      Countries
    </Link>
  );
}

function Header({ iso3, p, info }: { iso3: string; p: CountryProfile | undefined; info: DiseaseInfo }) {
  const region = REGIONS.find((r) => r.code === p?.who_region);
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="eyebrow text-teal">{info.label} intelligence</div>
        <h1 className="mt-1 text-lg font-semibold tracking-tight">{p?.name ?? iso3}</h1>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono">{iso3}</span>
          {region && <span>· {region.label} ({region.code})</span>}
          {!info.caseBased && p?.flu_season && <span>· {SEASON_LABEL[p.flu_season]} season pattern</span>}
          {p?.coverage && (
            <span className="flex items-center gap-1">
              · <TierBadge tier={p.coverage.tier} /> coverage tier
            </span>
          )}
          {p && !p.has_geometry && <span>· not drawn on the map (no separate boundary)</span>}
        </div>
      </div>
      {p?.has_geometry && (
        <Link
          href={withParams(`/surveillance?country=${iso3}`, diseaseParam(info.key))}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <Globe2 className="size-3.5" aria-hidden />
          Show on globe
        </Link>
      )}
    </div>
  );
}

function RecentStats({ p }: { p: CountryProfile }) {
  const r = p.recent;
  const lowN = r && r.positivity != null && (r.specimens_tested ?? 0) < MIN_SPECIMENS;
  return (
    <div>
      <div className="mb-2 text-[11px] text-muted-foreground">{windowLabel(p.recent_window)} (latest settled weeks)</div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Test positivity" value={r ? formatPct(r.positivity) : "No report"} note={lowN ? `Only ${formatInt(r?.specimens_tested)} specimens: unstable` : undefined} />
        <Stat label="Lab-confirmed detections" value={r ? formatInt(r.positives) : "No report"} />
        <Stat label="Specimens tested" value={r ? formatInt(r.specimens_tested) : "No report"} />
        <Stat
          label="Weeks reported"
          value={`${r?.weeks_reported ?? 0} of ${p.recent_window.weeks}`}
          note={`Last report: ${formatWeek(p.surveillance.last_reported_week)}`}
        />
      </div>
    </div>
  );
}

function History({ iso3 }: { iso3: string }) {
  const [range, setRange] = useState<(typeof RANGES)[number]["key"]>("5y");
  const profile = useCountryProfile(iso3);
  const meta = profile.data?.meta;
  const weeks = RANGES.find((r) => r.key === range)!.weeks;
  const to = meta?.latest_week ?? "";
  const from = meta ? (weeks ? addWeeks(meta.latest_week, -(weeks - 1)) : meta.first_week) : "";
  const series = useCountryTimeseries(meta ? iso3 : null, from, to);

  const [positivity, tests] = useMemo(() => {
    const pts = series.data?.points ?? [];
    const pos: WeeklyPoint[] = pts.map((s) => ({
      week: s.week_start,
      value: s.reported && (s.specimens_tested ?? 0) >= MIN_SPECIMENS ? s.positivity : null,
      provisional: s.is_provisional,
      details: [
        ["Detections", formatInt(s.positives)],
        ["Specimens tested", formatInt(s.specimens_tested)],
      ],
    }));
    const t: WeeklyPoint[] = pts.map((s) => ({
      week: s.week_start,
      value: s.reported ? s.specimens_tested : null,
      provisional: s.is_provisional,
      details: [["Detections", formatInt(s.positives)]],
    }));
    return [pos, t];
  }, [series.data]);

  return (
    <Card
      title="Surveillance history"
      subtitle={`Weekly · gaps are weeks without testing (or fewer than ${MIN_SPECIMENS} specimens for positivity), never zero · dashed / faded = provisional`}
      actions={
        <div className="grid grid-cols-4 gap-1 rounded-full border border-border bg-muted p-1 text-xs" role="radiogroup" aria-label="History range">
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              role="radio"
              aria-checked={range === r.key}
              onClick={() => setRange(r.key)}
              className={cn(
                "rounded-full px-3 py-1 transition-colors",
                range === r.key ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      }
    >
      {series.error && <QueryError error={series.error} />}
      <h3 className="text-[11px] text-muted-foreground">Test positivity</h3>
      <div className="h-56">
        {series.data && (
          <WeeklyChart
            points={positivity}
            kind="line"
            seriesName="Test positivity"
            formatValue={(v) => formatPct(v)}
            formatAxis={(v) => `${Math.round(v * 100)}%`}
            ariaLabel="Weekly test positivity"
          />
        )}
      </div>
      <h3 className="mt-3 text-[11px] text-muted-foreground">Specimens tested</h3>
      <div className="h-36">
        {series.data && (
          <WeeklyChart
            compact
            points={tests}
            kind="bar"
            seriesName="Specimens tested"
            formatValue={(v) => formatInt(v)}
            formatAxis={(v) => formatCompact(v)}
            ariaLabel="Weekly specimens tested"
          />
        )}
      </div>
    </Card>
  );
}

function ThresholdNote({ current, seasonType }: { current: ThresholdLevels | null; seasonType: string | null }) {
  if (seasonType === "YR") {
    return (
      <p className="mt-1 text-[11px] text-muted-foreground">
        No MEM thresholds: influenza circulates year-round here, and the Moving Epidemic Method assumes one epidemic per season.
      </p>
    );
  }
  if (!current) {
    return (
      <p className="mt-1 text-[11px] text-muted-foreground">
        No MEM thresholds for this season: they need at least 3 complete, non-COVID past seasons.
      </p>
    );
  }
  if (current.quality_note) {
    return (
      <p className="mt-1 text-[11px] text-muted-foreground">
        MEM thresholds for {current.season} are not shown: {current.quality_note}.
      </p>
    );
  }
  return (
    <p className="mt-1 text-[11px] text-muted-foreground">
      MEM levels for {current.season}: epidemic {formatPct(current.epidemic_threshold)}, medium {formatPct(current.medium)}, high{" "}
      {formatPct(current.high)}, very high {formatPct(current.very_high)} — from {current.n_seasons_used} past seasons
      (Moving Epidemic Method, R <span className="font-mono">mem</span> defaults; validated against it).
    </p>
  );
}

function Seasons({ iso3 }: { iso3: string }) {
  const seasons = useCountrySeasons(iso3);
  const d = seasons.data;
  const current = d?.seasons.find((s) => s.is_current);
  const usable = current?.thresholds && !current.thresholds.quality_note ? current.thresholds : null;
  return (
    <Card
      title="Seasonal profile"
      subtitle={d ? `${d.season_rule} Current season highlighted; earlier seasons grey, COVID-disrupted seasons dashed. Dashed horizontal lines: this season's MEM levels.` : "Loading…"}
    >
      {seasons.error && <QueryError error={seasons.error} />}
      {d && d.seasons.length > 0 && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
          <div className="h-72">
            <SeasonChart seasons={d.seasons} minSpecimens={d.min_specimens_for_peak} thresholds={usable} />
          </div>
          <div>
            <SeasonTable seasons={d.seasons} />
            <p className="mt-2 text-[11px] text-muted-foreground">
              Peaks use settled weeks with at least {d.min_specimens_for_peak} specimens.
            </p>
            <ThresholdNote current={current?.thresholds ?? null} seasonType={d.season_type} />
          </div>
        </div>
      )}
      {d && d.seasons.length === 0 && <p className="text-xs text-muted-foreground">{d.season_rule}</p>}
    </Card>
  );
}

function Context({ p }: { p: CountryProfile }) {
  const refYear = Number(p.meta.reference_week.slice(0, 4));
  const rows: { label: string; value: string | null; unit?: string; year: number | null; source?: string | null }[] = [
    {
      label: "Population",
      value: p.population ? formatCompact(p.population.value) : null,
      year: p.population?.year ?? null,
      source: p.population?.source,
    },
    ...p.health.map((h: HealthValue) => ({
      label: h.label,
      value: h.value == null ? null : h.value.toLocaleString("en-US", { maximumFractionDigits: 1 }),
      unit: h.unit,
      year: h.year,
      source: h.source,
    })),
  ];
  return (
    <Card title="Population and health-system context" subtitle="Latest available year · World Bank WDI (CC BY 4.0) · never estimated">
      <dl className="text-xs">
        {rows.map((r) => (
          <div key={r.label} className="flex items-baseline justify-between gap-3 border-b border-border/60 py-1.5 last:border-0">
            <dt className="text-muted-foreground">
              {r.label}
              {r.unit && <span className="ml-1 text-[10.5px] text-subtle-foreground">({r.unit})</span>}
            </dt>
            <dd className="metric text-right">
              {r.value == null ? (
                <span className="text-muted-foreground">Not available</span>
              ) : (
                <>
                  {r.value}
                  <span className={cn("ml-1.5 text-[10.5px]", r.year != null && refYear - r.year > STALE_YEARS ? "text-status-warn" : "text-muted-foreground")}>
                    {r.year}
                  </span>
                </>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Years in amber are more than {STALE_YEARS} years old.
      </p>
    </Card>
  );
}

function Coverage({ p }: { p: CountryProfile }) {
  const c = p.coverage;
  const rows: [string, string][] = c
    ? [
        ["Coverage tier", c.tier],
        ["Completeness", formatPct(c.completeness, 0)],
        ["Longest gap", `${c.longest_gap} weeks`],
        ["Median specimens per reported week", formatInt(c.median_tests)],
        ["Weeks since last report", c.weeks_since_last == null ? "—" : String(c.weeks_since_last)],
      ]
    : [];
  return (
    <Card
      title="Data coverage"
      subtitle={c ? `Profiled at reference week ${formatWeek(c.reference_week)}` : undefined}
    >
      <dl className="text-xs">
        <div className="flex justify-between gap-3 border-b border-border/60 py-1.5">
          <dt className="text-muted-foreground">Reporting since</dt>
          <dd className="metric">{formatWeek(p.surveillance.first_week)}</dd>
        </div>
        <div className="flex justify-between gap-3 border-b border-border/60 py-1.5">
          <dt className="text-muted-foreground">Weeks with testing</dt>
          <dd className="metric">{formatInt(p.surveillance.weeks_reported)}</dd>
        </div>
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b border-border/60 py-1.5 last:border-0">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="metric">{v}</dd>
          </div>
        ))}
      </dl>
      {!c && <p className="mt-2 text-[11px] text-muted-foreground">No coverage profile: not enough FluNet reporting.</p>}
      <ul className="mt-2 space-y-0.5 text-[11px] text-muted-foreground">
        {Object.entries(TIER_RULES).map(([t, rule]) => (
          <li key={t} className={cn(c?.tier === t && "text-foreground")}>
            <span className="font-semibold">{t}</span> — {rule}
          </li>
        ))}
      </ul>
    </Card>
  );
}
