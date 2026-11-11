"use client";

import { useIsFetching } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

/** Data requests running this long are usually the free API host starting up. */
const SLOW_MS = 5000;

/**
 * A notice while data has been loading for more than SLOW_MS: the hosted API sleeps when
 * idle and takes up to about a minute to start. Hidden as soon as loading stops.
 */
export function WakeNotice() {
  const fetching = useIsFetching() > 0;
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!fetching) return;
    const t = setTimeout(() => setSlow(true), SLOW_MS);
    return () => {
      clearTimeout(t);
      setSlow(false);
    };
  }, [fetching]);

  if (!fetching || !slow) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="panel-glass fixed bottom-4 left-1/2 z-50 flex max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-2.5 px-4 py-2.5 text-xs text-muted-foreground"
    >
      <Loader2 className="size-4 shrink-0 animate-spin text-primary" aria-hidden />
      <span>
        Still loading: the data server may be waking up (it pauses when idle on free hosting). This can take up to a
        minute.
      </span>
    </div>
  );
}
