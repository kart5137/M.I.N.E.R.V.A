import { Suspense } from "react";

import { OverviewDashboard } from "@/components/overview/overview-dashboard";

export default function OverviewPage() {
  // Filters are read from the URL, which needs a Suspense boundary under Cache Components.
  return (
    <Suspense fallback={null}>
      <OverviewDashboard />
    </Suspense>
  );
}
