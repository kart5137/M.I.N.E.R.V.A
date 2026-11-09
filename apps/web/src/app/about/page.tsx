import type { Metadata } from "next";

import { AboutView } from "@/components/intelligence/about-view";

export const metadata: Metadata = { title: "About the Data" };

export default function AboutPage() {
  return <AboutView />;
}
