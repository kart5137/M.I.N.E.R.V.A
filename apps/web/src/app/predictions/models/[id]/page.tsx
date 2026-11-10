import type { Metadata } from "next";
import { Suspense } from "react";

import { DiseaseGate } from "@/components/common/disease-gate";
import { ModelDetailView } from "@/components/predictions/model-detail";

export const metadata: Metadata = { title: "Model detail" };

export default function ModelPage() {
  return (
    <Suspense fallback={null}>
      <DiseaseGate feature="forecasting" title="Model detail">
        <ModelDetailView />
      </DiseaseGate>
    </Suspense>
  );
}
