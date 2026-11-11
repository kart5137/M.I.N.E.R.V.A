import type { Metadata } from "next";
import { Suspense } from "react";

import { DiseaseGate } from "@/components/common/disease-gate";
import { SurveillanceView } from "@/components/surveillance/surveillance-view";

export const metadata: Metadata = { title: "Global Surveillance" };

export default function SurveillancePage() {
  return (
    <Suspense fallback={null}>
      <DiseaseGate feature="surveillance" title="Global Surveillance">
        <SurveillanceView />
      </DiseaseGate>
    </Suspense>
  );
}
