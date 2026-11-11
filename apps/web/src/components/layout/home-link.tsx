"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { diseaseParam, useDisease, withParams } from "@/lib/filters";

/** Link to the home page (Overview) that keeps the selected disease. Needs <Suspense>. */
export function HomeLink({ className, children }: { className?: string; children: ReactNode }) {
  const disease = useDisease();
  return (
    <Link href={withParams("/", diseaseParam(disease))} aria-label="M.I.N.E.R.V.A. home" className={className}>
      {children}
    </Link>
  );
}
