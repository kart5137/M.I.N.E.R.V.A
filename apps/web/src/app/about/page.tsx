import type { Metadata } from "next";
import { Suspense } from "react";

import { AboutView } from "@/components/intelligence/about-view";

export const metadata: Metadata = { title: "About the Data" };

export default function AboutPage() {
  // The page follows the disease in the URL (useSearchParams), so it streams under Suspense.
  return (
    <Suspense fallback={null}>
      <AboutView />
    </Suspense>
  );
}
