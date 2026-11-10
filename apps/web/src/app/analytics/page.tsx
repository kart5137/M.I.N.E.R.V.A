import type { Metadata } from "next";
import { Suspense } from "react";

import { DiseaseGate } from "@/components/common/disease-gate";
import { AnalyticsView } from "@/components/analytics/analytics-view";

export const metadata: Metadata = { title: "Analytics" };

export default function AnalyticsPage() {
  return (
    <Suspense fallback={null}>
      <DiseaseGate feature="analytics" title="Analytics">
        <AnalyticsView />
      </DiseaseGate>
    </Suspense>
  );
}
