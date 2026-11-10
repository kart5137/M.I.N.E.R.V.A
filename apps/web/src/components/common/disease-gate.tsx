"use client";

import { CalendarClock } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { DISEASES, type Feature, FEATURE_LABELS } from "@/lib/diseases";
import { useFilters } from "@/lib/filters";

/**
 * Renders a page only when the selected disease has `feature`. Otherwise explains why
 * and offers a working switch back to influenza. Must sit under <Suspense>.
 */
export function DiseaseGate({
  feature,
  title,
  children,
}: {
  feature: Feature;
  title: string;
  children: React.ReactNode;
}) {
  const [filters, setFilters] = useFilters();
  const info = DISEASES[filters.disease];
  if (info.features[feature]) return <>{children}</>;
  return (
    <div className="flex flex-1 flex-col gap-4 p-4 lg:p-6">
      <PageHeader title={title} eyebrow={`${info.label} surveillance`} />
      <section className="panel flex max-w-xl items-start gap-3 p-5">
        <CalendarClock className="mt-0.5 size-5 shrink-0 text-teal" aria-hidden />
        <div>
          <h2 className="text-sm font-semibold">
            {FEATURE_LABELS[feature]} is not available for {info.label.toLowerCase()}
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {info.unavailable?.[feature] ??
              `${info.label} data is shown on the Overview, Global Surveillance, Countries and country pages.`}
          </p>
          <button
            type="button"
            onClick={() => setFilters({ disease: "influenza" })}
            className="mt-3 rounded-full bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground"
          >
            Show influenza {FEATURE_LABELS[feature].toLowerCase()}
          </button>
        </div>
      </section>
    </div>
  );
}
