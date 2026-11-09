"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api";
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
  const qs = new URLSearchParams();
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
    queryKey: ["alerts", f],
    queryFn: () => apiGet<AlertList>(`/alerts?${qs}`),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

export function useReports(page: number, iso3?: string | null) {
  const qs = new URLSearchParams({ page: String(page), page_size: "20" });
  if (iso3) qs.set("iso3", iso3);
  return useQuery({
    queryKey: ["reports", page, iso3],
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

export function useVerifyReport(id: number) {
  return useMutation({ mutationFn: () => apiGet<Verification>(`/reports/${id}/verify`) });
}

export function useGenerateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: GenerateReportRequest) => apiPost<GenerateReportResponse>("/reports/generate", req),
    onSuccess: (res) => {
      qc.setQueryData(["report", res.report.id], res.report);
      void qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

export function useAbout() {
  return useQuery({ queryKey: ["about"], queryFn: () => apiGet<About>("/about"), staleTime: STALE });
}
