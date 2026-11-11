"use client";

import { AnnualAbout } from "@/components/annual/annual-about";
import { ArrowRight, ExternalLink } from "lucide-react";
import Link from "next/link";

import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { useAbout } from "@/hooks/use-intelligence";
import { diseaseParam, useFilters, withParams } from "@/lib/filters";
import { formatInt, formatWeek } from "@/lib/format";
import { DEFAULT_DISEASE, isDiseaseKey, DISEASES } from "@/lib/diseases";
import type { About } from "@/lib/types";

import { ALERT_LABEL } from "./alert-ui";

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="panel p-4">
      <h2 className="text-sm font-medium">{title}</h2>
      {subtitle && <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

export function AboutView() {
  const [filters] = useFilters();
  const info = DISEASES[filters.disease];
  // Diseases without models or detection (malaria, cholera) have a sources-and-limits page.
  return info.grain === "year" || (!info.features.forecasting && !info.features.detection) ? (
    <AnnualAbout />
  ) : (
    <WeeklyAbout />
  );
}

function WeeklyAbout() {
  const q = useAbout();
  const d = q.data;
  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="About the Data"
        description="Where every number comes from, how it is processed, and what it cannot tell you."
      />
      {q.error && <QueryError error={q.error} />}
      {!d && !q.error && <div className="h-60 animate-pulse panel" />}
      {d && (
        <>
          <p className="rounded-md border border-status-warn/40 bg-status-warn/10 px-3 py-2 text-xs">
            M.I.N.E.R.V.A. (Monitoring &amp; Intelligence Network for Epidemic Risk, Visualisation and Alerts) is an analytical tool built on public surveillance data. It is not medical advice or
            public-health guidance, and it does not replace national or WHO assessments.
          </p>
          <Sources d={d} />
          <div className="grid gap-4 lg:grid-cols-2">
            <Tiers d={d} />
            <Pipeline d={d} />
          </div>
          <ModelCard d={d} />
          <DetectionCard d={d} />
          <Card title="Known limitations">
            <ul className="list-disc space-y-1.5 pl-5 text-xs text-muted-foreground">
              {d.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}

function Sources({ d }: { d: About }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {d.sources.map((s) => (
        <section key={s.key} className="flex flex-col panel p-4">
          <h2 className="text-sm font-medium">{s.name}</h2>
          <dl className="mt-2 space-y-1.5 text-xs">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Licence</dt>
              <dd className="text-right">{s.licence ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">Last ingestion</dt>
              <dd className="text-right">{when(s.last_ingestion)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">{s.key === "natural_earth" ? "Boundaries stored" : "Rows stored"}</dt>
              <dd className="metric text-right">{formatInt(s.stored_rows)}</dd>
            </div>
          </dl>
          {s.notes && <p className="mt-2 text-[11px] text-muted-foreground">{s.notes}</p>}
          {s.attribution && (
            <p className="mt-2 rounded bg-muted px-2 py-1.5 text-[11px]">
              <span className="text-muted-foreground">Attribution: </span>
              {s.attribution}
            </p>
          )}
          {s.url && (
            <a href={s.url} target="_blank" rel="noreferrer" className="mt-auto inline-flex items-center gap-1 pt-3 text-xs text-muted-foreground hover:text-foreground">
              {new URL(s.url).hostname} <ExternalLink className="size-3" />
            </a>
          )}
        </section>
      ))}
    </div>
  );
}

function Tiers({ d }: { d: About }) {
  const total = d.tiers.reduce((a, t) => a + t.countries, 0);
  return (
    <Card
      title="Coverage tiers"
      subtitle={`Profiled at reference week ${formatWeek(d.coverage_reference_week)} over the last 5 years · ${total} areas`}
    >
      <table className="w-full text-xs">
        <tbody>
          {d.tiers.map((t) => (
            <tr key={t.tier} className="border-b border-border/60 last:border-0">
              <td className="py-2 pr-3 align-top font-semibold">{t.tier}</td>
              <td className="py-2 pr-3 text-muted-foreground">{t.rule}</td>
              <td className="metric py-2 text-right align-top">{t.countries}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-muted-foreground">Forecasts are produced for tiers A and B only.</p>
    </Card>
  );
}

/** Disease-specific wording; the API's `meta.disease` says which disease the page shows. */
function isDengue(d: About): boolean {
  return d.meta.disease === "dengue";
}

/** A link that keeps the page's disease. */
function href(d: About, path: string): string {
  const key = isDiseaseKey(d.meta.disease) ? d.meta.disease : DEFAULT_DISEASE;
  return withParams(path, diseaseParam(key));
}

const DENGUE_STEPS = [
  ["Ingest", "WHO Global Dengue Surveillance, World Bank population and ERA5 weather (Open-Meteo) are downloaded, validated and loaded; revisions to past periods are kept."],
  ["Profile", "Each country's series is profiled into a coverage tier (3-year window); weekly and monthly reporters are kept apart, and recent periods are marked provisional."],
  ["Forecast", "Weekly incidence per 100,000: baselines, and Random Forest and XGBoost with and without weather, are backtested on past origins; the best model that beats seasonal-naive is used."],
  ["Detect", "Endemic channels (each country's usual weekly range), risk levels, anomalies and hotspots on weekly incidence are computed from stored data."],
  ["Alert & report", "Fixed rules turn detection outputs into alerts; reports are deterministic templates over stored facts."],
];

function Pipeline({ d }: { d: About }) {
  const steps = isDengue(d) ? DENGUE_STEPS : [
    ["Ingest", "WHO FluNet, Natural Earth and World Bank are downloaded, validated and loaded; revisions to past weeks are kept."],
    ["Profile", "Each country's series is profiled into a coverage tier; recent weeks are marked provisional."],
    ["Forecast", "Baselines, Random Forest and XGBoost are backtested on past origins; the best model that beats seasonal-naive is used."],
    ["Detect", "MEM thresholds, risk levels, anomalies and hotspots are computed from stored data."],
    ["Alert & report", "Fixed rules turn detection outputs into alerts; reports are deterministic templates over stored facts."],
  ];
  return (
    <Card title="How the data flows" subtitle={`Reference week ${formatWeek(d.meta.reference_week)} · latest week ${formatWeek(d.meta.latest_week)}`}>
      <ol className="space-y-2 text-xs">
        {steps.map(([k, v], i) => (
          <li key={k} className="flex gap-3">
            <span className="metric grid size-5 shrink-0 place-items-center rounded-full bg-muted text-[10.5px]">{i + 1}</span>
            <span>
              <span className="font-medium">{k}.</span> <span className="text-muted-foreground">{v}</span>
            </span>
          </li>
        ))}
      </ol>
    </Card>
  );
}

const DENGUE_MODEL_ROWS = [
  ["Target", "Weekly reported incidence per 100,000 per country, modelled as log(incidence + one case per 100,000); tree models learn the change from the latest week."],
  ["Horizons", "1, 2 and 4 weeks ahead; one pooled model per horizon (direct strategy). Weekly reporters in tiers A and B with a population."],
  ["Inputs", "Lagged incidence and trends, same week last year, time of year, reported case volume, neighbouring-country incidence and latitude; weather models add 18 lagged ERA5 temperature, rainfall and humidity features and their anomalies."],
  ["Weather test", "Each tree model is fitted with and without weather on the same rows; a weather model is used only if it wins the backtest. The model card reports the difference with a bootstrap interval."],
  ["Intervals", "Split conformal, calibrated separately by weekly case count; 80% and 95%."],
  ["Explanations", "SHAP contributions per forecast and global importance."],
];

function ModelCard({ d }: { d: About }) {
  const f = d.forecast_run;
  const dengue = isDengue(d);
  return (
    <Card
      title={dengue ? "Model card: dengue incidence forecasts" : "Model card: influenza test positivity forecasts"}
      subtitle={f ? `Run ${f.run_key} · trained to ${formatWeek(f.train_end)} · backtest ${formatWeek(f.eval_start)} – ${formatWeek(f.eval_end)}` : "No forecasting run yet."}
    >
      {f && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <dl className="space-y-2 text-xs">
            {(dengue ? DENGUE_MODEL_ROWS : [
              ["Target", "Weekly test positivity per country, modelled on the logit scale."],
              ["Horizons", "1, 2 and 4 weeks ahead; one pooled model per horizon (direct strategy)."],
              ["Inputs", "Lagged positivity and trends, same week last year, calendar, testing volume, transmission-zone and neighbouring-country positivity, latitude and season type."],
              ["Evaluation", "Rolling-origin backtest every 2 weeks, expanding window, no future data; MAE, RMSE, MASE, skill vs seasonal-naive, interval coverage."],
              ["Intervals", "Split conformal, calibrated separately by testing volume; 80% and 95%."],
              ["Explanations", "SHAP contributions per forecast and global importance."],
            ]).map(([k, v]) => (
              <div key={k}>
                <dt className="font-medium">{k}</dt>
                <dd className="text-muted-foreground">{v}</dd>
              </div>
            ))}
          </dl>
          <div>
            <table className="w-full text-xs">
              <thead className="text-[11px] text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="py-1.5 text-left font-normal">Horizon</th>
                  <th className="py-1.5 text-left font-normal">Active model</th>
                  <th className="py-1.5 text-right font-normal">MASE</th>
                  <th className="py-1.5 text-right font-normal">Skill</th>
                  <th className="py-1.5 text-right font-normal">80% cov.</th>
                </tr>
              </thead>
              <tbody className="metric">
                {f.models.map((m) => (
                  <tr key={m.id} className="border-b border-border/60 last:border-0">
                    <td className="py-1.5">{m.horizon_weeks} wk</td>
                    <td className="py-1.5">
                      <Link href={href(d, `/predictions/models/${m.id}`)} className="hover:underline">{m.label}</Link>
                    </td>
                    <td className="py-1.5 text-right">{m.metrics.mase?.toFixed(3) ?? "—"}</td>
                    <td className="py-1.5 text-right">
                      {m.metrics.skill_vs_snaive == null ? "—" : `${(m.metrics.skill_vs_snaive * 100).toFixed(1)}%`}
                    </td>
                    <td className="py-1.5 text-right">
                      {m.metrics.coverage_80 == null ? "—" : `${(m.metrics.coverage_80 * 100).toFixed(0)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Lower MASE is better; skill is the error reduction vs the same week last year. Full card:{" "}
              <span className="font-mono">docs/models/{dengue ? "dengue-incidence.md" : "influenza-positivity.md"}</span>.
            </p>
            <Link href={href(d, "/predictions")} className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              Prediction Center <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </div>
      )}
    </Card>
  );
}

function DetectionCard({ d }: { d: About }) {
  const r = d.detection_run;
  const dengue = isDengue(d);
  return (
    <Card
      title="Methods card: detection and alerts"
      subtitle={r ? `Run ${r.run_key} · finished ${when(r.finished_at)}` : "No detection run yet."}
    >
      {r && (
        <div className="grid gap-4 text-xs lg:grid-cols-2">
          <dl className="space-y-2">
            {dengue ? (
              <div>
                <dt className="font-medium">Endemic channel</dt>
                <dd className="text-muted-foreground">
                  Each country&apos;s usual range for every week: median, 75th (top of the channel) and 90th percentiles of
                  the same week ±1 in up to 7 earlier complete years, the highest year left out (at least 4 remaining), as
                  used in dengue surveillance in the Americas. {r.thresholds_current_usable ?? 0} countries have a channel
                  this year. Moving Epidemic Method levels are not used for dengue: most dengue years were too irregular.
                </dd>
              </div>
            ) : (
              <div>
                <dt className="font-medium">Epidemic thresholds (Moving Epidemic Method)</dt>
                <dd className="text-muted-foreground">
                  Python port of R <span className="font-mono">mem</span> 2.19 with its defaults, validated to match it exactly.{" "}
                  Temperate countries only; {r.thresholds_current_usable ?? 0} countries have usable levels this season.
                </dd>
              </div>
            )}
            <div>
              <dt className="font-medium">Risk</dt>
              <dd className="text-muted-foreground">
                2-week forecast vs {dengue ? "the endemic channel" : "MEM levels"}: low {r.risk?.low ?? 0}, moderate{" "}
                {r.risk?.moderate ?? 0}, high {r.risk?.high ?? 0}.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Anomalies</dt>
              <dd className="text-muted-foreground">
                Above the seasonal upper band (90th percentile of the same weeks in the latest 5{dengue ? "" : " non-COVID"} years
                {dengue ? ", on log incidence" : ""}) with an EWMA signal; {formatInt(r.anomalies?.seasonal_ewma)} flagged
                country-weeks since 2023. Isolation Forest is a secondary signal only.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Hotspots</dt>
              <dd className="text-muted-foreground">
                Getis-Ord Gi* and Local Moran&apos;s I on 4-week {dengue ? "incidence" : "positivity"}, queen contiguity with 4-nearest fallback, 999
                permutations, Benjamini–Hochberg FDR at 0.05; {r.hotspots?.windows ?? 0} weekly windows.
              </dd>
            </div>
          </dl>
          <div>
            <h3 className="font-medium">Alert rules</h3>
            <table className="mt-1.5 w-full">
              <tbody>
                {Object.entries(ALERT_LABEL).map(([k, label]) => (
                  <tr key={k} className="border-b border-border/60 last:border-0">
                    <td className="py-1.5 pr-3">{label}</td>
                    <td className="metric py-1.5 text-right">{formatInt(r.alerts?.by_type[k] ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Active alerts since January 2025. Alerts that a later run no longer produces (e.g. after a data revision) are kept
              and marked retracted.
            </p>
            <Link href={href(d, "/reports")} className="mt-2 inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
              Reports &amp; Alerts <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </div>
      )}
    </Card>
  );
}
