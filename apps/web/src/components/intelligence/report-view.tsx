"use client";

import { ArrowLeft, CheckCircle2, Download, Loader2, ShieldCheck, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";

import { WeeklyChart } from "@/components/charts/weekly-chart";
import { QueryError } from "@/components/common/query-state";
import { useReport, useVerifyReport } from "@/hooks/use-intelligence";
import { ApiError } from "@/lib/api";
import { formatInt, formatPct, formatWeek } from "@/lib/format";
import type { Verification } from "@/lib/types";

import { MarkdownView } from "./markdown-view";

export function ReportView() {
  const { id: raw } = useParams<{ id: string }>();
  const id = Number(raw);
  const params = useSearchParams();
  const q = useReport(Number.isFinite(id) ? id : null);
  const verify = useVerifyReport(id);
  const r = q.data;

  if (q.error) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="p-6">
        <Back />
        {missing ? <p className="mt-4 text-sm text-muted-foreground">No report with id {raw}.</p> : <QueryError error={q.error} />}
      </div>
    );
  }

  const download = () => {
    if (!r) return;
    const blob = new Blob([r.rendered_md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `report-${r.id}-${r.scope}${r.iso3 ? `-${r.iso3}` : ""}-${r.period_end}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <Back />
      {!r && <div className="h-40 animate-pulse rounded-lg border border-border bg-card" />}
      {r && (
        <>
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold tracking-tight">{r.title}</h1>
              <p className="mt-0.5 text-[12px] text-muted-foreground">
                Report #{r.id} · template v{r.template_version} · created{" "}
                {new Date(r.created_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })} · inputs{" "}
                <span className="font-mono" title={r.inputs_sha256}>{r.inputs_sha256.slice(0, 16)}…</span>
              </p>
              {params.get("reused") === "1" && (
                <p className="mt-1 text-[12px] text-muted-foreground">
                  An identical report already existed (same inputs), so it was reused instead of stored twice.
                </p>
              )}
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={() => verify.mutate()} disabled={verify.isPending}
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-xs hover:bg-accent disabled:opacity-50">
                {verify.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <ShieldCheck className="size-3.5" />}
                Verify reproducibility
              </button>
              <button type="button" onClick={download}
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-xs hover:bg-accent">
                <Download className="size-3.5" /> Markdown
              </button>
            </div>
          </header>
          {verify.error && <QueryError error={verify.error} />}
          {verify.data && <VerifyResult v={verify.data} />}

          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-medium">Weekly test positivity</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              From the report&apos;s stored facts; the highlighted span is the report period.
            </p>
            <div className="mt-2 h-48">
              <WeeklyChart
                points={r.content.weekly.map((w) => ({
                  week: w.week_start,
                  value: (w.specimens_tested ?? 0) >= 10 ? w.positivity : null,
                  provisional: w.provisional,
                  details: [
                    ["Detections", formatInt(w.positives)],
                    ["Specimens", formatInt(w.specimens_tested)],
                  ],
                }))}
                kind="line"
                seriesName="Positivity"
                formatValue={(v) => formatPct(v)}
                formatAxis={(v) => `${Math.round(v * 100)}%`}
                highlight={{ start: r.content.period.start, end: r.content.period.end }}
                ariaLabel="Weekly test positivity in the report and comparison periods"
              />
            </div>
          </section>

          <article className="rounded-lg border border-border bg-card p-5">
            <MarkdownView md={r.rendered_md} />
          </article>
          <p className="text-[11px] text-muted-foreground">
            Period {formatWeek(r.period_start)} – {formatWeek(r.period_end)}. Generated by a fixed template from stored data;
            no text is written by a language model.
          </p>
        </>
      )}
    </div>
  );
}

function Back() {
  return (
    <Link href="/reports?tab=reports" className="inline-flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-3.5" /> Reports
    </Link>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <li className="flex items-center gap-2">
      <Icon className={ok ? "size-4 text-status-ok" : "size-4 text-status-error"} aria-hidden />
      <span>{label}</span>
      <span className="text-muted-foreground">{ok ? "yes" : "no"}</span>
    </li>
  );
}

function VerifyResult({ v }: { v: Verification }) {
  return (
    <section className="rounded-lg border border-border bg-card p-4 text-xs">
      <h2 className="text-sm font-medium">Reproducibility check</h2>
      <ul className="mt-2 space-y-1.5">
        <Check ok={v.rendering_identical} label="Stored facts re-render to the stored Markdown, byte for byte" />
        <Check ok={v.inputs_identical} label="Gathering the facts again from the database gives the same inputs hash" />
        <Check ok={v.regenerated_identical} label="Regenerating now gives the stored Markdown, byte for byte" />
      </ul>
      {!v.inputs_identical && (
        <p className="mt-2 text-muted-foreground">
          The stored data changed since this report was generated (sections: {v.changed_sections.join(", ")}), for example a new
          weekly ingestion, forecast or detection run. The report keeps its original facts.
        </p>
      )}
      <p className="mt-2 font-mono text-[10.5px] text-muted-foreground">
        stored {v.stored_sha256}
        <br />
        now&nbsp;&nbsp;&nbsp; {v.current_sha256}
      </p>
    </section>
  );
}
