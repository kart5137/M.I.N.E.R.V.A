import type { Metadata } from "next";
import { Suspense } from "react";

import { DiseaseGate } from "@/components/common/disease-gate";
import { ReportView } from "@/components/intelligence/report-view";

export const metadata: Metadata = { title: "Report" };

export default function ReportPage() {
  return (
    <Suspense fallback={null}>
      <DiseaseGate feature="reports" title="Report">
        <ReportView />
      </DiseaseGate>
    </Suspense>
  );
}
