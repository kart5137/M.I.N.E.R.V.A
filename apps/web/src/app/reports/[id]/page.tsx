import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportView } from "@/components/intelligence/report-view";

export const metadata: Metadata = { title: "Report" };

export default function ReportPage() {
  return (
    <Suspense fallback={null}>
      <ReportView />
    </Suspense>
  );
}
