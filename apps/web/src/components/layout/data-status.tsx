"use client";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { type PlatformState, usePlatformStatus } from "@/hooks/use-platform-status";
import { API_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

const LABELS: Record<PlatformState["kind"], { text: string; tone: string }> = {
  loading: { text: "Checking…", tone: "bg-status-idle" },
  api_offline: { text: "API offline", tone: "bg-status-error" },
  db_offline: { text: "Database offline", tone: "bg-status-error" },
  not_migrated: { text: "Schema not set up", tone: "bg-status-warn" },
  no_data: { text: "No data loaded", tone: "bg-status-warn" },
  ready: { text: "Live data", tone: "bg-status-ok" },
  error: { text: "Status error", tone: "bg-status-error" },
};

function formatWeek(iso: string | null) {
  if (!iso) return "—";
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function DataStatus() {
  const state = usePlatformStatus();
  const label = LABELS[state.kind];
  const status = "status" in state ? state.status : null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="flex h-8 items-center gap-2 rounded-md border border-border bg-card px-2.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <span className={cn("size-1.5 rounded-full", label.tone)} aria-hidden />
          <span>{label.text}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 text-xs">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Platform status
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
          <dt className="text-muted-foreground">API</dt>
          <dd className="truncate">{state.kind === "api_offline" ? "Unreachable" : API_BASE_URL}</dd>
          <dt className="text-muted-foreground">Database</dt>
          <dd>{status ? "Connected" : state.kind === "db_offline" ? "Unreachable" : "—"}</dd>
          <dt className="text-muted-foreground">PostGIS</dt>
          <dd>{status?.postgis_version ?? "—"}</dd>
          <dt className="text-muted-foreground">Schema</dt>
          <dd className="font-mono">{status?.schema_revision ?? "—"}</dd>
        </dl>
        {status && status.diseases.length > 0 && (
          <div className="mt-3 border-t border-border pt-2">
            {status.diseases.map((d) => (
              <dl key={d.key} className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                <dt className="col-span-2 font-medium text-foreground">{d.name}</dt>
                <dt className="text-muted-foreground">Reference week</dt>
                <dd className="metric">{formatWeek(d.reference_week)}</dd>
                <dt className="text-muted-foreground">Provisional from</dt>
                <dd className="metric">{formatWeek(d.provisional_from)}</dd>
                <dt className="text-muted-foreground">Country-weeks</dt>
                <dd className="metric">{d.country_weeks.toLocaleString("en-US")}</dd>
              </dl>
            ))}
          </div>
        )}
        {state.kind === "error" && <p className="mt-2 text-destructive">{state.message}</p>}
      </PopoverContent>
    </Popover>
  );
}
