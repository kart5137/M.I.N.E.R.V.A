"use client";

import { useEffect, useState } from "react";

/** Live border-box height of an element (0 until mounted). */
export function useElementHeight(el: HTMLElement | null): number {
  const [height, setHeight] = useState(0);
  useEffect(() => {
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setHeight(entry.borderBoxSize[0]?.blockSize ?? el.offsetHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return height;
}

/** Whether a media query matches (false during SSR and the first client render). */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const update = () => setMatches(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [query]);
  return matches;
}
