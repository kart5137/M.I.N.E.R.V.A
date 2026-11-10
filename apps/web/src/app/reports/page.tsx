import type { Metadata } from "next";
import { Suspense } from "react";

import { DiseaseGate } from "@/components/common/disease-gate";
import { ReportsView } from "@/components/intelligence/reports-view";

export const metadata: Metadata = { title: "Reports & Alerts" };

export default function ReportsPage() {
  return (
    <Suspense fallback={null}>
      <DiseaseGate feature="reports" title="Reports & Alerts">
        <ReportsView />
      </DiseaseGate>
    </Suspense>
  );
}
