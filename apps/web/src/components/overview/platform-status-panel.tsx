"use client";

import { CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import { type PlatformState, usePlatformStatus } from "@/hooks/use-platform-status";

type StepState = "done" | "pending" | "failed";

function Step({ state, title, detail }: { state: StepState; title: string; detail: ReactNode }) {
  const Icon = state === "done" ? CheckCircle2 : state === "failed" ? XCircle : CircleDashed;
  const tone =
    state === "done" ? "text-status-ok" : state === "failed" ? "text-status-error" : "text-status-idle";
  return (
    <li className="flex gap-3">
      <Icon className={`mt-0.5 size-4 shrink-0 ${tone}`} aria-hidden />
      <div>
        <div className="text-[13px] font-medium">{title}</div>
        <div className="text-xs text-muted-foreground">{detail}</div>
      </div>
    </li>
  );
}

function steps(s: PlatformState): { api: StepState; db: StepState; schema: StepState; data: StepState } {
  switch (s.kind) {
    case "loading":
      return { api: "pending", db: "pending", schema: "pending", data: "pending" };
    case "api_offline":
    case "error":
      return { api: "failed", db: "pending", schema: "pending", data: "pending" };
    case "db_offline":
      return { api: "done", db: "failed", schema: "pending", data: "pending" };
    case "not_migrated":
      return { api: "done", db: "done", schema: "pending", data: "pending" };
    case "no_data":
      return { api: "done", db: "done", schema: "done", data: "pending" };
    case "ready":
      return { api: "done", db: "done", schema: "done", data: "done" };
  }
}

const code = (t: string) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">{t}</code>;

export function PlatformStatusPanel() {
  const state = usePlatformStatus();
  const s = steps(state);
  const status = "status" in state ? state.status : null;

  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Platform readiness
      </h2>
      <ol className="mt-3 space-y-3">
        <Step
          state={s.api}
          title="API service"
          detail={s.api === "failed" ? <>Start it with {code("uvicorn app.main:app")}</> : "FastAPI reachable"}
        />
        <Step
          state={s.db}
          title="Database"
          detail={
            s.db === "failed" ? (
              <>Start PostGIS with {code("docker compose up -d")}</>
            ) : status?.postgis_version ? (
              `PostgreSQL + PostGIS ${status.postgis_version}`
            ) : (
              "PostgreSQL + PostGIS"
            )
          }
        />
        <Step
          state={s.schema}
          title="Schema"
          detail={status?.schema_revision ? `Revision ${status.schema_revision}` : <>Run {code("alembic upgrade head")}</>}
        />
        <Step
          state={s.data}
          title="Surveillance data"
          detail={s.data === "done" ? "WHO FluNet loaded" : "WHO FluNet ingestion arrives in milestone M2"}
        />
      </ol>
      <p className="mt-4 border-t border-border pt-3 text-xs leading-relaxed text-muted-foreground">
        Indicators, trends and forecasts appear here once real data is loaded. This dashboard never
        shows placeholder or simulated figures.
      </p>
    </section>
  );
}
