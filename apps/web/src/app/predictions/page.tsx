import type { Metadata } from "next";
import { Suspense } from "react";

import { DiseaseGate } from "@/components/common/disease-gate";
import { PredictionCenter } from "@/components/predictions/prediction-center";

export const metadata: Metadata = { title: "Prediction Center" };

export default function PredictionsPage() {
  return (
    <Suspense fallback={null}>
      <DiseaseGate feature="forecasting" title="Prediction Center">
        <PredictionCenter />
      </DiseaseGate>
    </Suspense>
  );
}
