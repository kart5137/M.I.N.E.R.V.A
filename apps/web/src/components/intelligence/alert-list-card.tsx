"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { QueryError } from "@/components/common/query-state";
import { useAlerts } from "@/hooks/use-intelligence";
import { formatWeek } from "@/lib/format";
import { cn } from "@/lib/utils";

import { AlertSeverityBadge, AlertTypeLabel, alertText } from "./alert-ui";

/** Latest active alerts (Overview: all countries in the region; country page: one country). */
export function AlertListCard({
  region = null,
  iso3 = null,
  to = null,
  limit = 6,
  className,
  children,
}: {
  region?: string | null;
  iso3?: string | null;
  to?: string | null;
  limit?: number;
  className?: string;
  children?: React.ReactNode;
}) {
  const q = useAlerts({ region, iso3, to, status: "active", pageSize: limit });
  const d = q.data;
  return (
    <section className={cn("flex flex-col rounded-lg border border-border bg-card", className)}>
      <header className="flex items-start justify-between gap-2 border-b border-border p-4 pb-3">
        <div>
          <h2 className="text-sm font-medium">{iso3 ? "Alerts" : "Latest alerts"}</h2>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {d ? `${d.total} active${to ? ` up to ${formatWeek(to)}` : ""} · rule-based, from stored detection outputs` : "Loading…"}
          </p>
        </div>
        <Link
          href={iso3 ? `/reports?iso3=${iso3}` : `/reports${region ? `?region=${region}` : ""}`}
          className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          All alerts <ArrowRight className="size-3.5" />
        </Link>
      </header>
      {q.error && <QueryError error={q.error} className="p-4" />}
      {d && d.items.length === 0 && <p className="p-4 text-xs text-muted-foreground">No alerts.</p>}
      <ul className="divide-y divide-border/60">
        {d?.items.map((a) => (
          <li key={a.id} className="space-y-1 px-4 py-2.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                <AlertTypeLabel t={a.alert_type} />
                <AlertSeverityBadge s={a.severity} />
              </span>
              <span className="metric text-[11px] text-muted-foreground">{formatWeek(a.week_start)}</span>
            </div>
            <p className="text-muted-foreground">
              {iso3 ? (
                alertText(a.title, a.name)
              ) : (
                <>
                  <Link href={`/countries/${a.iso3}`} className="text-foreground hover:underline">{a.name}</Link>
                  {": "}
                  {alertText(a.title, a.name)}
                </>
              )}
            </p>
          </li>
        ))}
      </ul>
      {children && <div className="mt-auto border-t border-border p-4">{children}</div>}
    </section>
  );
}
