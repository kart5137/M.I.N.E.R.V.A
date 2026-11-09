import type { Metadata } from "next";
import { Suspense } from "react";

import { PredictionCenter } from "@/components/predictions/prediction-center";

export const metadata: Metadata = { title: "Prediction Center" };

export default function PredictionsPage() {
  return (
    <Suspense fallback={null}>
      <PredictionCenter />
    </Suspense>
  );
}
