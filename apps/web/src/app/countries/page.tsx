import type { Metadata } from "next";
import { Suspense } from "react";

import { CountriesTable } from "@/components/countries/countries-table";

export const metadata: Metadata = { title: "Countries" };

export default function CountriesPage() {
  return (
    <Suspense fallback={null}>
      <CountriesTable />
    </Suspense>
  );
}
