"use client";

import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { addWeeks, formatWeek, isoWeekLabel, weeksBetween } from "@/lib/format";
import type { ResponseMeta } from "@/lib/types";
import { cn } from "@/lib/utils";

const PLAY_INTERVAL_MS = 700;
const COMMIT_DELAY_MS = 180;

export interface TimeSliderProps {
  meta: ResponseMeta;
  /** Current last week of the window. */
  week: string;
  onChange: (week: string) => void;
  /** Called while playing so the next week can be fetched ahead of time. */
  onPrefetch?: (week: string) => void;
  className?: string;
}

/** Week slider over the full record. The provisional tail is shaded on the track. */
export function TimeSlider({ meta, week, onChange, onPrefetch, className }: TimeSliderProps) {
  const total = weeksBetween(meta.first_week, meta.latest_week);
  const [draft, setDraft] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const commitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const index = draft ?? weeksBetween(meta.first_week, week);
  const shown = addWeeks(meta.first_week, index);
  const provisional = meta.provisional_from !== null && shown >= meta.provisional_from;
  const provStartPct = meta.provisional_from
    ? (weeksBetween(meta.first_week, meta.provisional_from) / total) * 100
    : 100;

  const commit = (i: number) => {
    const clamped = Math.min(Math.max(i, 0), total);
    setDraft(clamped);
    if (commitTimer.current) clearTimeout(commitTimer.current);
    commitTimer.current = setTimeout(() => {
      onChange(addWeeks(meta.first_week, clamped));
      setDraft(null);
    }, COMMIT_DELAY_MS);
  };

  // Playback: one week per tick, stopping at the latest week.
  const latest = useRef({ week, onChange, onPrefetch });
  useEffect(() => {
    latest.current = { week, onChange, onPrefetch };
  });
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const { week: w, onChange: change, onPrefetch: prefetch } = latest.current;
      if (w >= meta.latest_week) {
        setPlaying(false);
        return;
      }
      const next = addWeeks(w, 1);
      change(next);
      if (next < meta.latest_week) prefetch?.(addWeeks(next, 1));
    }, PLAY_INTERVAL_MS);
    return () => clearInterval(id);
  }, [playing, meta.latest_week]);

  useEffect(() => () => {
    if (commitTimer.current) clearTimeout(commitTimer.current);
  }, []);

  const atEnd = shown >= meta.latest_week;

  return (
    <div className={cn("rounded-lg border border-border bg-card/90 p-3 backdrop-blur", className)}>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => {
            if (!playing && atEnd) onChange(addWeeks(meta.latest_week, -52));
            setPlaying((p) => !p);
          }}
          aria-label={playing ? "Pause playback" : "Play week by week"}
          className="grid size-8 shrink-0 place-items-center rounded-md bg-primary text-primary-foreground hover:bg-primary/90"
        >
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </button>
        <button
          type="button"
          onClick={() => commit(index - 1)}
          disabled={index <= 0}
          aria-label="Previous week"
          className="grid size-8 shrink-0 place-items-center rounded-md border border-border text-muted-foreground hover:text-foreground disabled:opacity-40"
        >
          <ChevronLeft className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => commit(index + 1)}
          disabled={atEnd}
          aria-label="Next week"
          className="grid size-8 shrink-0 place-items-center rounded-md border border-border text-muted-foreground hover:text-foreground disabled:opacity-40"
        >
          <ChevronRight className="size-4" />
        </button>

        <div className="ml-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="whitespace-nowrap text-sm font-semibold">{formatWeek(shown)}</span>
            <span className="hidden font-mono text-[11px] text-muted-foreground sm:inline">{isoWeekLabel(shown)}</span>
            {provisional && (
              <span className="rounded bg-status-warn/15 px-1.5 text-[10.5px] text-status-warn">Provisional</span>
            )}
          </div>
          <div className="text-[10.5px] text-muted-foreground">Window ends this week</div>
        </div>

        <button
          type="button"
          onClick={() => {
            setPlaying(false);
            onChange(meta.reference_week);
          }}
          disabled={shown === meta.reference_week}
          aria-label="Latest settled week"
          className="ml-auto shrink-0 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-40"
        >
          <span className="sm:hidden">Latest</span>
          <span className="hidden sm:inline">Latest settled week</span>
        </button>
      </div>

      <div className="relative mt-3">
        <div
          className="pointer-events-none absolute top-1/2 h-1.5 -translate-y-1/2 rounded-r-full bg-status-warn/40"
          style={{ left: `${provStartPct}%`, right: 0 }}
          aria-hidden
        />
        <input
          type="range"
          min={0}
          max={total}
          step={1}
          value={index}
          onChange={(e) => {
            setPlaying(false);
            commit(Number(e.target.value));
          }}
          aria-label="Week"
          aria-valuetext={`${formatWeek(shown)}${provisional ? ", provisional" : ""}`}
          className="relative w-full accent-[var(--primary)]"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>{formatWeek(meta.first_week)}</span>
          <span>{formatWeek(meta.latest_week)}</span>
        </div>
      </div>
    </div>
  );
}
