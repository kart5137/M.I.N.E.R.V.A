import type { Metadata } from "next";
import { Suspense } from "react";

import { DiseaseGate } from "@/components/common/disease-gate";
import { HotspotsView } from "@/components/hotspots/hotspots-view";

export const metadata: Metadata = { title: "Hotspots & Anomalies" };

export default function HotspotsPage() {
  return (
    <Suspense fallback={null}>
      <DiseaseGate feature="detection" title="Hotspots & Anomalies">
        <HotspotsView />
      </DiseaseGate>
    </Suspense>
  );
}
