"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
import { DEFAULT_DISEASE } from "@/lib/diseases";
import { forDisease, useDisease } from "@/lib/filters";
import type {
  About,
  AlertList,
  GenerateReportRequest,
  GenerateReportResponse,
  ReportDetail,
  ReportList,
  Verification,
} from "@/lib/types";

const STALE = 5 * 60_000;

export interface AlertFilters {
  region: string | null;
  iso3?: string | null;
  type?: string | null;
  severity?: string | null;
  status?: "active" | "retracted" | "all";
  from?: string | null;
  to?: string | null;
  page?: number;
  pageSize?: number;
}

export function useAlerts(f: AlertFilters) {
  const disease = useDisease();
  const qs = new URLSearchParams();
  if (disease !== DEFAULT_DISEASE) qs.set("disease", disease);
  if (f.region) qs.set("region", f.region);
  if (f.iso3) qs.set("iso3", f.iso3);
  if (f.type) qs.set("type", f.type);
  if (f.severity) qs.set("severity", f.severity);
  if (f.status) qs.set("status", f.status);
  if (f.from) qs.set("from", f.from);
  if (f.to) qs.set("to", f.to);
  qs.set("page", String(f.page ?? 1));
  qs.set("page_size", String(f.pageSize ?? 50));
  return useQuery({
    queryKey: ["alerts", disease, f],
    queryFn: () => apiGet<AlertList>(`/alerts?${qs}`),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useReports(page: number, iso3?: string | null) {
  const disease = useDisease();
  const qs = new URLSearchParams({ page: String(page), page_size: "20" });
  if (iso3) qs.set("iso3", iso3);
  if (disease !== DEFAULT_DISEASE) qs.set("disease", disease);
  return useQuery({
    queryKey: ["reports", disease, page, iso3],
    queryFn: () => apiGet<ReportList>(`/reports?${qs}`),
    placeholderData: keepPreviousData,
  });
}

export function useReport(id: number | null) {
  return useQuery({
    queryKey: ["report", id],
    queryFn: () => apiGet<ReportDetail>(`/reports/${id}`),
    enabled: id != null,
    staleTime: Infinity,
  });
}

/** Verifies against the report's own disease (a report page may be opened from a link). */
export function useVerifyReport(id: number, disease: string = DEFAULT_DISEASE) {
  return useMutation({
    mutationFn: () =>
      apiGet<Verification>(`/reports/${id}/verify${disease !== DEFAULT_DISEASE ? `?disease=${disease}` : ""}`),
  });
}

export function useGenerateReport() {
  const qc = useQueryClient();
  const disease = useDisease();
  return useMutation({
    mutationFn: (req: GenerateReportRequest) =>
      apiPost<GenerateReportResponse>(forDisease("/reports/generate", disease), req),
    onSuccess: (res) => {
      qc.setQueryData(["report", res.report.id], res.report);
      void qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

export function useAbout() {
  const disease = useDisease();
  return useQuery({
    queryKey: ["about", disease],
    queryFn: () => apiGet<About>(forDisease("/about", disease)),
    staleTime: STALE,
  });
}
