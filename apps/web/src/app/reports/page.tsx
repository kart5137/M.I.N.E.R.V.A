import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportsView } from "@/components/intelligence/reports-view";

export const metadata: Metadata = { title: "Reports & Alerts" };

export default function ReportsPage() {
  return (
    <Suspense fallback={null}>
      <ReportsView />
    </Suspense>
  );
}
