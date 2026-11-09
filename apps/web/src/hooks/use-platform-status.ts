"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError, apiGet } from "@/lib/api";
import type { MetaStatus } from "@/lib/types";

export type PlatformState =
  | { kind: "loading" }
  | { kind: "api_offline" }
  | { kind: "db_offline" }
  | { kind: "not_migrated"; status: MetaStatus }
  | { kind: "no_data"; status: MetaStatus }
  | { kind: "ready"; status: MetaStatus }
  | { kind: "error"; message: string };

/** Polls /meta/status and reduces it to one explicit platform state. */
export function usePlatformStatus(): PlatformState {
  const query = useQuery({
    queryKey: ["meta", "status"],
    queryFn: () => apiGet<MetaStatus>("/meta/status"),
    refetchInterval: 30_000,
    retry: false,
  });

  if (query.isPending) return { kind: "loading" };
  if (query.error) {
    const err = query.error;
    if (err instanceof ApiError && err.code === "api_unreachable") return { kind: "api_offline" };
    if (err instanceof ApiError && err.code === "database_unavailable") return { kind: "db_offline" };
    return { kind: "error", message: err.message };
  }
  const status = query.data;
  if (!status.schema_revision) return { kind: "not_migrated", status };
  if (!status.diseases.some((d) => d.country_weeks > 0)) return { kind: "no_data", status };
  return { kind: "ready", status };
}
