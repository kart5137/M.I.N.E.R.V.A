import type { Metadata } from "next";
import { Suspense } from "react";

import { CountryIntelligence } from "@/components/country/country-intelligence";

export const metadata: Metadata = { title: "Country Intelligence" };

/** The country code is runtime data; the client component reads it under Suspense. */
export default function CountryPage() {
  return (
    <Suspense fallback={null}>
      <CountryIntelligence />
    </Suspense>
  );
}
