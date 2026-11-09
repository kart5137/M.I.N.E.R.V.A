import type { Metadata } from "next";
import { Suspense } from "react";

import { HotspotsView } from "@/components/hotspots/hotspots-view";

export const metadata: Metadata = { title: "Hotspots & Anomalies" };

export default function HotspotsPage() {
  return (
    <Suspense fallback={null}>
      <HotspotsView />
    </Suspense>
  );
}
