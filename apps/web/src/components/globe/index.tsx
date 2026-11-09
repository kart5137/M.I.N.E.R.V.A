"use client";

import dynamic from "next/dynamic";

/** WebGL globe; browser-only, so it is never prerendered. */
export const Globe = dynamic(() => import("./globe").then((m) => m.Globe), {
  ssr: false,
  loading: () => (
    <div className="grid h-full w-full place-items-center bg-[var(--globe-space)] text-xs text-muted-foreground">
      Initialising globe…
    </div>
  ),
});

export type { CountryProps, GlobeProps } from "./globe";
