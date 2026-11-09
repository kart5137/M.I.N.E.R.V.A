import type { Metadata } from "next";

import { SurveillanceView } from "@/components/surveillance/surveillance-view";

export const metadata: Metadata = { title: "Global Surveillance" };

export default function SurveillancePage() {
  return <SurveillanceView />;
}
