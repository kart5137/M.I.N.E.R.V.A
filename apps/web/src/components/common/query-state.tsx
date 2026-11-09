import { ApiError } from "@/lib/api";

/** Explicit error message for a failed query; never falls back to placeholder data. */
export function QueryError({ error, className }: { error: Error; className?: string }) {
  const msg =
    error instanceof ApiError && error.code === "api_unreachable"
      ? "The API server is not reachable."
      : error.message;
  return (
    <div role="alert" className={className ?? "p-4 text-xs text-status-error"}>
      Could not load data: {msg}
    </div>
  );
}
