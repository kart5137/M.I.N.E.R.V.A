import { Activity, Flame, TrendingUp, TriangleAlert } from "lucide-react";

import type { AlertSeverity, AlertType } from "@/lib/types";
import { cn } from "@/lib/utils";

export const ALERT_LABEL: Record<AlertType, string> = {
  new_anomaly: "New anomaly",
  new_hotspot: "New hot spot",
  risk_escalation: "Risk escalation",
  sustained_growth: "Sustained growth",
};

export const ALERT_ICON: Record<AlertType, typeof Activity> = {
  new_anomaly: Activity,
  new_hotspot: Flame,
  risk_escalation: TriangleAlert,
  sustained_growth: TrendingUp,
};

/** Alert title without the leading "Country: ", capitalised. */
export function alertText(title: string, name: string): string {
  const t = title.startsWith(`${name}: `) ? title.slice(name.length + 2) : title;
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export const SEVERITY_ORDER: AlertSeverity[] = ["high", "medium", "low"];

const SEVERITY_TONE: Record<AlertSeverity, string> = {
  high: "border-status-error/50 text-status-error",
  medium: "border-status-warn/50 text-status-warn",
  low: "border-border text-muted-foreground",
};

/** Severity always as text; colour only reinforces it. */
export function AlertSeverityBadge({ s, className }: { s: AlertSeverity; className?: string }) {
  return (
    <span className={cn("inline-block rounded border px-1.5 text-[10.5px] capitalize", SEVERITY_TONE[s], className)}>
      {s}
    </span>
  );
}

export function AlertTypeLabel({ t }: { t: AlertType }) {
  const Icon = ALERT_ICON[t];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Icon className="size-3.5 text-muted-foreground" aria-hidden />
      {ALERT_LABEL[t]}
    </span>
  );
}
