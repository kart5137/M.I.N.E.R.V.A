"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { CHART, EChart, type EChartsOption } from "@/components/charts/echart";
import { Provenance } from "@/components/common/provenance";
import { QueryError } from "@/components/common/query-state";
import { useModelDetail } from "@/hooks/use-forecasts";
import { ApiError } from "@/lib/api";
import { diseaseParam, useDisease, withParams } from "@/lib/filters";
import { formatPct, formatRate, formatWeek } from "@/lib/format";
import { type Metric, metricFor } from "@/lib/metric";
import type { ModelDetail as Detail, Metrics } from "@/lib/types";
import { cn } from "@/lib/utils";

import { err, num, signedPct } from "./prediction-center";

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="panel p-4">
      <h2 className="text-sm font-medium">{title}</h2>
      {subtitle && <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

const rows = (m: Metric): [keyof Metrics, string, (v: number | null) => string][] => [
  ["mae", "MAE", err(m)],
  ["rmse", "RMSE", err(m)],
  ["mase", "MASE", (v) => num(v)],
  ["skill_vs_snaive", "Skill vs seasonal naive", signedPct],
  ["coverage_80", "80% interval coverage", (v) => formatPct(v, 1)],
  ["coverage_95", "95% interval coverage", (v) => formatPct(v, 1)],
];

export function ModelDetailView() {
  const { id } = useParams<{ id: string }>();
  const m = metricFor(useDisease());
  const detail = useModelDetail(Number(id));
  const d = detail.data;

  if (detail.error) {
    const missing = detail.error instanceof ApiError && detail.error.status === 404;
    return (
      <div className="p-6">
        <Back />
        <h1 className="mt-4 text-lg font-semibold tracking-tight">{missing ? "Model not found" : "Model"}</h1>
        {missing ? <p className="mt-1 text-sm text-muted-foreground">No model version {id}.</p> : <QueryError error={detail.error} />}
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <Back />
      <div>
        <h1 className="text-lg font-semibold tracking-tight">
          {d ? `${d.label} · ${d.horizon_weeks}-week horizon` : "Loading…"}
          {d?.is_active && <span className="ml-2 rounded bg-status-ok/15 px-1.5 align-middle text-[11px] font-normal text-status-ok">active</span>}
        </h1>
        {d && (
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            {d.kind === "ml" ? "Pooled machine-learning model" : "Baseline rule"} · target:{" "}
            {m.key === "incidence" ? "weekly dengue incidence per 100,000" : "weekly test positivity"} · run {d.run_key} · trained{" "}
            {new Date(d.trained_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}
          </p>
        )}
        {d?.selection_note && <p className="mt-2 text-xs text-muted-foreground">{d.selection_note}</p>}
      </div>

      {d && (
        <>
          <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
            <Card title="Backtest metrics" subtitle={`${d.metrics.n_obs ?? 0} country-weeks over ${d.metrics.n_origins ?? 0} origins`}>
              <table className="w-full text-xs">
                <thead className="text-[11px] text-muted-foreground">
                  <tr className="border-b border-border">
                    <th className="py-1.5 text-left font-normal">Metric</th>
                    <th className="py-1.5 text-right font-normal">{d.label}</th>
                    <th className="py-1.5 text-right font-normal">Seasonal naive</th>
                  </tr>
                </thead>
                <tbody className="metric">
                  {rows(m).map(([k, label, f]) => (
                    <tr key={k} className="border-b border-border/60 last:border-0">
                      <td className="py-1.5 text-muted-foreground">{label}</td>
                      <td className="py-1.5 text-right">{f(d.metrics[k] as number | null)}</td>
                      <td className="py-1.5 text-right text-muted-foreground">{f(d.reference[k] as number | null)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card
              title="Error by forecast origin"
              subtitle={`Mean absolute error across countries for forecasts made at each origin (${m.key === "incidence" ? "cases per 100,000" : "pp"}).`}
            >
              <div className="h-56">
                <ErrorChart data={d} m={m} />
              </div>
            </Card>
          </div>

          {d.importance.length > 0 && (
            <Card
              title="Global feature importance"
              subtitle={
                m.key === "incidence"
                  ? "Mean |SHAP| over the latest forecasts (change in log incidence). In a pooled model, latitude and weather values partly act as country identifiers."
                  : "Mean |SHAP| over the latest forecasts (log-odds scale). In a pooled model, latitude and season type partly act as country identifiers."
              }
            >
              <div className="h-[420px]">
                <ImportanceChart data={d} />
              </div>
            </Card>
          )}

          <CountryTable data={d} m={m} />
          <Card title="Model record">
            <dl className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
              <Item k="Training targets" v={d.train_start ? `${formatWeek(d.train_start)} – ${formatWeek(d.train_end)}` : `up to ${formatWeek(d.train_end)}`} />
              <Item k="Artefact" v={d.artefact_uri ?? "— (rule, nothing stored)"} mono />
              <Item k="Code version" v={d.git_sha ? d.git_sha.slice(0, 10) : "—"} mono />
              <Item k="Features" v={d.features ? `${d.features.length}` : "—"} />
              {d.hyperparams &&
                Object.entries(d.hyperparams).map(([k, v]) => <Item key={k} k={k} v={String(v)} mono />)}
            </dl>
          </Card>
          <Provenance meta={d.meta} />
        </>
      )}
    </div>
  );
}

function Item({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3 border-b border-border/60 py-1">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className={cn("text-right", mono && "font-mono text-[11px]")}>{v}</dd>
    </div>
  );
}

function Back() {
  return (
    <Link href={withParams("/predictions", diseaseParam(useDisease()))} className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-3.5" aria-hidden />
      Prediction Center
    </Link>
  );
}

function ErrorChart({ data, m }: { data: Detail; m: Metric }) {
  const option = useMemo<EChartsOption>(() => ({
    animation: false,
    grid: { left: 44, right: 12, top: 12, bottom: 28 },
    tooltip: {
      trigger: "axis",
      ...CHART.tooltip,
      formatter: (p: { dataIndex: number }[]) => {
        const e = data.error_by_origin[p[0]?.dataIndex ?? 0];
        return `<b>${formatWeek(e.origin_week)}</b><br/>MAE ${err(m)(e.mae)} · ${e.n} countries`;
      },
    },
    xAxis: {
      type: "category",
      data: data.error_by_origin.map((e) => e.origin_week),
      axisLine: { lineStyle: { color: CHART.axis } },
      axisTick: { show: false },
      axisLabel: {
        color: CHART.muted,
        fontSize: 10,
        hideOverlap: true,
        formatter: (v: string) => new Date(`${v}T00:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" }),
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      splitLine: { lineStyle: { color: CHART.grid } },
      axisLabel: {
        color: CHART.muted,
        fontSize: 10,
        formatter: (v: number) => (m.key === "incidence" ? formatRate(v) : `${(v * 100).toFixed(0)}`),
      },
    },
    series: [
      {
        type: "bar",
        data: data.error_by_origin.map((e) => e.mae),
        itemStyle: { color: CHART.series, borderRadius: [2, 2, 0, 0] },
        barCategoryGap: "25%",
      },
    ],
  }), [data, m]);
  return <EChart option={option} ariaLabel="Mean absolute error by forecast origin" />;
}

function ImportanceChart({ data }: { data: Detail }) {
  const option = useMemo<EChartsOption>(() => {
    const items = [...data.importance].slice(0, 16).reverse();
    return {
      animation: false,
      grid: { left: 190, right: 48, top: 4, bottom: 20 },
      tooltip: { ...CHART.tooltip, formatter: (p: { name: string; value: number }) => `${p.name}: ${p.value.toFixed(3)}` },
      xAxis: { type: "value", splitLine: { lineStyle: { color: CHART.grid } }, axisLabel: { color: CHART.muted, fontSize: 10 } },
      yAxis: {
        type: "category",
        data: items.map((i) => i.label),
        axisLine: { lineStyle: { color: CHART.axis } },
        axisTick: { show: false },
        axisLabel: { color: CHART.ink, fontSize: 11 },
      },
      series: [
        {
          type: "bar",
          data: items.map((i) => i.value),
          barWidth: 12,
          itemStyle: { color: CHART.series, borderRadius: 2 },
          label: { show: true, position: "right", color: CHART.muted, fontSize: 10, formatter: (p: { value: number }) => p.value.toFixed(2) },
        },
      ],
    };
  }, [data]);
  return <EChart option={option} ariaLabel="Global feature importance" />;
}

function CountryTable({ data, m }: { data: Detail; m: Metric }) {
  const [order, setOrder] = useState<"best" | "worst">("worst");
  const rows = useMemo(() => {
    const withMase = data.countries.filter((c) => c.metrics.mase != null);
    const sorted = [...withMase].sort((a, b) => (a.metrics.mase ?? 0) - (b.metrics.mase ?? 0));
    return order === "best" ? sorted : sorted.reverse();
  }, [data, order]);
  return (
    <Card title="By country" subtitle={`${data.countries.length} countries · MASE uses each country's in-sample seasonal-naive error; skill compares with seasonal naive on the same weeks.`}>
      <div className="mb-2 flex gap-1 text-xs" role="radiogroup" aria-label="Order">
        {(["worst", "best"] as const).map((o) => (
          <button
            key={o}
            type="button"
            role="radio"
            aria-checked={order === o}
            onClick={() => setOrder(o)}
            className={cn("rounded px-2 py-1", order === o ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground")}
          >
            {o === "worst" ? "Highest MASE first" : "Lowest MASE first"}
          </button>
        ))}
      </div>
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-card text-[11px] text-muted-foreground">
            <tr className="border-b border-border">
              <th className="py-1.5 text-left font-normal">Country</th>
              <th className="py-1.5 text-right font-normal">MAE</th>
              <th className="py-1.5 text-right font-normal">MASE</th>
              <th className="py-1.5 text-right font-normal">Skill</th>
              <th className="py-1.5 text-right font-normal">80% coverage</th>
              <th className="py-1.5 text-right font-normal">Weeks</th>
            </tr>
          </thead>
          <tbody className="metric">
            {rows.map((c) => (
              <tr key={c.iso3} className="border-b border-border/60 last:border-0">
                <td className="py-1.5">
                  <Link
                    href={withParams(
                      `/predictions?country=${c.iso3}&h=${data.horizon_weeks}&model=${data.model_type}`,
                      m.key === "incidence" ? "disease=dengue" : "",
                    )}
                    className="hover:text-primary"
                  >
                    {c.name}
                  </Link>
                </td>
                <td className="py-1.5 text-right">{err(m)(c.metrics.mae)}</td>
                <td className="py-1.5 text-right">{num(c.metrics.mase, 2)}</td>
                <td className="py-1.5 text-right text-muted-foreground">{signedPct(c.metrics.skill_vs_snaive)}</td>
                <td className="py-1.5 text-right text-muted-foreground">{formatPct(c.metrics.coverage_80, 0)}</td>
                <td className="py-1.5 text-right text-muted-foreground">{c.metrics.n_obs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
