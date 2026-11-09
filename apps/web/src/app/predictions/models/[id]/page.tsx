import type { Metadata } from "next";
import { Suspense } from "react";

import { ModelDetailView } from "@/components/predictions/model-detail";

export const metadata: Metadata = { title: "Model detail" };

export default function ModelPage() {
  return (
    <Suspense fallback={null}>
      <ModelDetailView />
    </Suspense>
  );
}
