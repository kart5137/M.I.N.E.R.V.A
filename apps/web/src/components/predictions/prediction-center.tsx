"use client";

import { ArrowRight, CheckCircle2, Info } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { Provenance } from "@/components/common/provenance";
import { QueryError } from "@/components/common/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { useBacktest, useCountryForecasts, useExplanation, useModelRun } from "@/hooks/use-forecasts";
import { useCountries, useCountryTimeseries } from "@/hooks/use-surveillance";
import { diseaseParam, updateSearchParams, useDisease, withParams } from "@/lib/filters";
import { addWeeks, formatPct, formatRate, formatWeek } from "@/lib/format";
import { type Metric, metricFor } from "@/lib/metric";
import { MIN_SPECIMENS } from "@/lib/positivity-scale";
import type { Metrics, ModelSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

import { BacktestChart, ForecastChart, ShapWaterfall } from "./forecast-charts";

const HORIZONS = [1, 2, 4] as const;
const HISTORY_WEEKS = 26;

export const pp = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(2)} pp`);
/** Forecast errors in the target's unit: percentage points of positivity, or incidence per 100,000. */
export const err = (m: Metric) => (v: number | null | undefined) =>
  m.key === "positivity" ? pp(v) : v == null ? "—" : `${formatRate(v)} /100k`;
export const signedPct = (v: number | null | undefined) =>
  v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v * 100).toFixed(1)}%`;
export const num = (v: number | null | undefined, d = 3) => (v == null ? "—" : v.toFixed(d));

function Card({ title, subtitle, actions, children, className }: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
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

function Select({ label, value, onChange, children }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className="h-8 min-w-44 rounded-md border border-border bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        {children}
      </select>
    </label>
  );
}

/** Default country per disease: a large tier-A reporter. */
const DEFAULT_COUNTRY = { influenza: "USA", dengue: "BRA" } as const;

export function PredictionCenter() {
  const params = useSearchParams();
  const disease = useDisease();
  const m = metricFor(disease);
  const run = useModelRun();
  const countries = useCountries({ disease, region: null, q: "", sort: "name", order: "asc", page: 1, pageSize: 300 });
  const eligible = useMemo(
    () => (countries.data?.items ?? []).filter((c) => c.tier === "A" || c.tier === "B"),
    [countries.data],
  );

  const iso3 = (params.get("country") ?? DEFAULT_COUNTRY[disease]).toUpperCase();
  const h = HORIZONS.find((x) => String(x) === params.get("h")) ?? 1;
  const versions = (run.data?.models ?? []).filter((m) => m.horizon_weeks === h);
  const active = versions.find((m) => m.is_active);
  const modelType = params.get("model") ?? active?.model_type ?? "";
  const selected = versions.find((m) => m.model_type === modelType) ?? active;

  const fc = useCountryForecasts(iso3);
  const ref = fc.data?.meta.reference_week;
  const latest = fc.data?.meta.latest_week;
  const history = useCountryTimeseries(ref ? iso3 : null, ref ? addWeeks(ref, -(HISTORY_WEEKS - 1)) : "", latest ?? "", disease);
  const modelForecasts = (fc.data?.forecasts ?? []).filter((f) => f.model_type === selected?.model_type);
  const forecastH = modelForecasts.find((f) => f.horizon_weeks === h);
  const explanation = useExplanation(forecastH?.has_explanation ? forecastH.id : null);
  const backtest = useBacktest(fc.data?.eligible ? iso3 : null, selected?.id ?? null);
  const countryName = eligible.find((c) => c.iso3 === iso3)?.name ?? countries.data?.items.find((c) => c.iso3 === iso3)?.name ?? iso3;

  if (run.error) return <div className="p-6"><QueryError error={run.error} /></div>;
  if (run.data && !run.data.run_key) {
    return (
      <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
        <PageHeader title="Prediction Center" description="No forecasting run yet." />
        <p className="text-sm text-muted-foreground">
          Train and store forecasts with <code className="rounded bg-muted px-1 font-mono text-xs">ei forecast run</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader
        title="Prediction Center"
        description={
          run.data
            ? `${m.key === "incidence" ? "Weekly dengue incidence per 100,000" : "Weekly influenza test positivity"} · forecasts from the reference week ${formatWeek(run.data.train_end)} · run ${run.data.run_key}`
            : "Loading…"
        }
      />

      {run.data && <ActiveModels models={run.data.models} m={m} />}

      <section className="flex flex-wrap items-end gap-3 panel p-3">
        <Select label="Country (coverage tier A or B)" value={iso3} onChange={(v) => updateSearchParams({ country: v })}>
          {!eligible.some((c) => c.iso3 === iso3) && <option value={iso3}>{countryName}</option>}
          {eligible.map((c) => (
            <option key={c.iso3} value={c.iso3}>
              {c.name}
            </option>
          ))}
        </Select>
        <div className="flex flex-col gap-1 text-[11px] text-muted-foreground">
          Horizon
          <div className="flex gap-1 rounded-full border border-border bg-muted p-1 text-xs" role="radiogroup" aria-label="Horizon">
            {HORIZONS.map((x) => (
              <button
                key={x}
                type="button"
                role="radio"
                aria-checked={h === x}
                onClick={() => updateSearchParams({ h: x === 1 ? null : x, model: null })}
                className={cn("rounded px-2.5 py-1", h === x ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
              >
                {x} week{x > 1 ? "s" : ""}
              </button>
            ))}
          </div>
        </div>
        <Select label="Model" value={selected?.model_type ?? ""} onChange={(v) => updateSearchParams({ model: v === active?.model_type ? null : v })}>
          {versions.map((m) => (
            <option key={m.id} value={m.model_type}>
              {m.label}
              {m.is_active ? " (active)" : ""}
            </option>
          ))}
        </Select>
        {selected && (
          <Link href={withParams(`/predictions/models/${selected.id}`, diseaseParam(disease))} className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            Model details <ArrowRight className="size-3.5" />
          </Link>
        )}
      </section>

      {fc.error && <QueryError error={fc.error} />}
      {fc.data && !fc.data.eligible && (
        <p className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
          <Info className="size-4 shrink-0" aria-hidden />
          {countryName}: {fc.data.reason}
        </p>
      )}

      {fc.data?.eligible && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
          <Card
            title={`${countryName} · ${selected?.label ?? ""}`}
            subtitle={`Observed ${m.key === "incidence" ? "incidence per 100,000" : "positivity"} (last ${HISTORY_WEEKS} weeks; hollow points are provisional) and forecasts for 1, 2 and 4 weeks ahead with 80% (darker) and 95% intervals. The axis fits the 80% interval; see the table for full 95% ranges.`}
          >
            <div className="h-72">
              {history.data && (
                <ForecastChart history={history.data.points} forecasts={modelForecasts} minSpecimens={MIN_SPECIMENS} m={m} />
              )}
            </div>
          </Card>
          <Card title="Forecasts" subtitle={`From the week of ${formatWeek(modelForecasts[0]?.origin_week)}`}>
            <table className="w-full text-xs">
              <thead className="text-[11px] text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="py-1.5 text-left font-normal">Week</th>
                  <th className="py-1.5 text-right font-normal">Forecast{m.key === "incidence" ? " /100k" : ""}</th>
                  <th className="py-1.5 text-right font-normal">80%</th>
                  <th className="py-1.5 text-right font-normal">95%</th>
                </tr>
              </thead>
              <tbody className="metric">
                {modelForecasts.map((f) => (
                  <tr key={f.id} className={cn("border-b border-border/60 last:border-0", f.horizon_weeks === h && "bg-accent/40")}>
                    <td className="py-1.5">
                      {formatWeek(f.target_week)}
                      <span className="ml-1 text-[10.5px] text-muted-foreground">+{f.horizon_weeks}</span>
                    </td>
                    <td className="py-1.5 text-right font-medium">{m.format(f.point)}</td>
                    <td className="py-1.5 text-right text-muted-foreground">
                      {m.formatBound(f.lo80)}–{m.formatBound(f.hi80)}
                    </td>
                    <td className="py-1.5 text-right text-muted-foreground">
                      {m.formatBound(f.lo95)}–{m.formatBound(f.hi95)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {m.key === "positivity" && modelForecasts.some((f) => f.hi95 != null && f.lo95 != null && f.hi95 - f.lo95 > 0.5) && (
              <p className="mt-2 rounded border border-status-warn/40 bg-status-warn/10 px-2 py-1.5 text-[11px] text-foreground">
                Few specimens are tested here, so weekly positivity is noisy and the 95% interval is very wide.
                The point forecast is less reliable than for high-testing countries.
              </p>
            )}
            <p className="mt-2 text-[11px] text-muted-foreground">
              Intervals are conformal, calibrated separately by {m.key === "incidence" ? "weekly case count" : "testing volume"}:
              built from this model&apos;s backtest errors and scaled by recent volatility. In the backtest, the 80% interval
              held the observed value {formatPct(selected?.metrics.coverage_80, 0)} of the time.
            </p>
          </Card>
        </div>
      )}

      {fc.data?.eligible && selected && (
        <div className="grid gap-4 xl:grid-cols-2">
          <Card
            title={`Why ${m.format(forecastH?.point)}${m.key === "incidence" ? " per 100k" : ""} for the week of ${formatWeek(forecastH?.target_week)}?`}
            subtitle={
              selected.kind === "baseline"
                ? "Baselines are fixed rules, so there is nothing to explain feature by feature."
                : m.key === "incidence"
                  ? "SHAP contributions to the change from this week, on the log scale (log of incidence plus one case per 100,000), largest first. Red raises the forecast, blue lowers it."
                  : "SHAP contributions on the log-odds scale, largest first. Red raises the forecast, blue lowers it."
            }
          >
            {selected.kind === "baseline" ? (
              <p className="text-xs text-muted-foreground">
                {selected.label} is a fixed rule, not a learned model:{" "}
                {(BASELINE_RULES[selected.model_type] ?? "").replaceAll("positivity", m.key === "incidence" ? "incidence" : "positivity")}
              </p>
            ) : explanation.error ? (
              <QueryError error={explanation.error} />
            ) : (
              explanation.data && (
                <>
                  <div className="h-80">
                    <ShapWaterfall data={explanation.data} />
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {m.key === "incidence"
                      ? `Starting point: this week's incidence plus the model's average change → this forecast ${m.format(explanation.data.point)} per 100k.`
                      : `Average prediction ${formatPct(expit(explanation.data.base_value ?? 0))} → this forecast ${formatPct(explanation.data.point)}.`}
                  </p>
                </>
              )
            )}
          </Card>
          <Card title={`Backtest in ${countryName}`} subtitle={`${selected.label}, ${h}-week horizon: what it forecast at each past origin vs. what was observed. Shaded: 80% interval.`}>
            {backtest.error ? (
              <QueryError error={backtest.error} />
            ) : (
              <div className="h-80">{backtest.data && <BacktestChart data={backtest.data} m={m} />}</div>
            )}
          </Card>
        </div>
      )}

      {run.data && (
        <MetricsTable
          versions={versions}
          countryMetrics={fc.data?.country_metrics ?? {}}
          horizon={h}
          countryName={countryName}
          selected={selected?.model_type}
          m={m}
          evalStart={run.data.eval_start}
          evalEnd={run.data.eval_end}
        />
      )}
      {run.data && <Provenance meta={run.data.meta} />}
    </div>
  );
}

const BASELINE_RULES: Record<string, string> = {
  seasonal_naive: "the forecast is the positivity observed in the same week one year earlier.",
  last_value: "the forecast is the positivity observed in the most recent week.",
  moving_average_4: "the forecast is the average positivity of the last four weeks.",
};

function expit(x: number) {
  return 1 / (1 + Math.exp(-x));
}

function ActiveModels({ models, m }: { models: ModelSummary[]; m: Metric }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {HORIZONS.map((h) => {
        const a = models.find((m) => m.horizon_weeks === h && m.is_active);
        return (
          <section key={h} className="panel p-3.5">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{h}-week horizon</span>
              {a && <CheckCircle2 className="size-4 text-status-ok" aria-label="Active model" />}
            </div>
            <div className="mt-1 text-base font-semibold">{a?.label ?? "—"}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              MAE {err(m)(a?.metrics.mae)} · skill vs seasonal naive {signedPct(a?.metrics.skill_vs_snaive)}
            </div>
            {a?.selection_note && <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{a.selection_note}</p>}
          </section>
        );
      })}
    </div>
  );
}

function MetricsTable({
  versions,
  countryMetrics,
  horizon,
  countryName,
  selected,
  m,
  evalStart,
  evalEnd,
}: {
  m: Metric;
  evalStart: string | null;
  evalEnd: string | null;
  versions: ModelSummary[];
  countryMetrics: Record<string, Metrics>;
  horizon: number;
  countryName: string;
  selected?: string;
}) {
  const rows = [...versions].sort((a, b) => (a.metrics.mase ?? 9) - (b.metrics.mase ?? 9));
  return (
    <Card
      title={`Backtest metrics · ${horizon}-week horizon`}
      subtitle={`All models are scored on the same country-weeks. MAE in ${m.key === "incidence" ? "cases per 100,000 per week" : "percentage points of positivity"}; MASE < 1 beats each country's in-sample seasonal-naive error.`}
    >
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Backtest metrics table">
        <table className="w-full min-w-[760px] text-xs">
          <thead className="text-[11px] text-muted-foreground">
            <tr className="border-b border-border">
              <th className="py-1.5 text-left font-normal">Model</th>
              <th className="py-1.5 text-right font-normal">MAE</th>
              <th className="py-1.5 text-right font-normal">RMSE</th>
              <th className="py-1.5 text-right font-normal">MASE</th>
              <th className="py-1.5 text-right font-normal">Skill vs seasonal naive</th>
              <th className="py-1.5 text-right font-normal">80% coverage</th>
              <th className="py-1.5 text-right font-normal">95% coverage</th>
              <th className="py-1.5 pl-4 text-right font-normal">{countryName} MAE</th>
              <th className="py-1.5 text-right font-normal">{countryName} MASE</th>
            </tr>
          </thead>
          <tbody className="metric">
            {rows.map((v) => {
              const c = countryMetrics[`${v.model_type}:${horizon}`];
              return (
                <tr key={v.id} className={cn("border-b border-border/60 last:border-0", v.model_type === selected && "bg-accent/40")}>
                  <td className="py-1.5">
                    <Link
                      href={withParams(`/predictions/models/${v.id}`, m.key === "incidence" ? "disease=dengue" : "")}
                      className="hover:text-primary"
                    >
                      {v.label}
                    </Link>
                    {v.is_active && <span className="ml-1.5 rounded bg-status-ok/15 px-1 text-[10px] text-status-ok">active</span>}
                    {v.kind === "baseline" && <span className="ml-1.5 text-[10px] text-muted-foreground">baseline</span>}
                  </td>
                  <td className="py-1.5 text-right">{err(m)(v.metrics.mae)}</td>
                  <td className="py-1.5 text-right text-muted-foreground">{err(m)(v.metrics.rmse)}</td>
                  <td className="py-1.5 text-right">{num(v.metrics.mase)}</td>
                  <td className="py-1.5 text-right">{signedPct(v.metrics.skill_vs_snaive)}</td>
                  <td className="py-1.5 text-right text-muted-foreground">{formatPct(v.metrics.coverage_80, 0)}</td>
                  <td className="py-1.5 text-right text-muted-foreground">{formatPct(v.metrics.coverage_95, 0)}</td>
                  <td className="py-1.5 pl-4 text-right">{err(m)(c?.mae)}</td>
                  <td className="py-1.5 text-right">{num(c?.mase)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Backtest: forecast origins every 2 weeks from {formatWeek(evalStart)} to {formatWeek(evalEnd)}; models
        retrained every 8 weeks on data available at the time. It uses today&apos;s revised data, so real-time accuracy can be lower.
      </p>
    </Card>
  );
}
