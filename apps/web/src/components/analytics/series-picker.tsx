"use client";

/**
 * "Add series" for the Analytics comparison: a popover with a search box and a grouped
 * list (World and WHO regions, then countries). Type to filter (accents ignored), arrow
 * keys to move, Enter to add. Each row previews the colour the new series will get.
 */

import { Plus, Search } from "lucide-react";
import { Popover as P } from "radix-ui";
import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface SeriesOption {
  value: string;
  label: string;
  /** Short code shown on the right (ISO3 or region code). */
  code?: string;
  /** Muted second word, e.g. the WHO region of a country. */
  hint?: string;
  group: "aggregate" | "country";
}

const fold = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

export function SeriesPicker({
  options,
  onAdd,
  nextColor,
  countriesLabel = "Countries",
  remaining,
}: {
  options: SeriesOption[];
  onAdd: (value: string) => void;
  /** Colour the next added series will take. */
  nextColor: string;
  countriesLabel?: string;
  /** Series slots still free. */
  remaining: number;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const f = fold(q.trim());
    if (!f) return options;
    return options.filter((o) => fold(o.label).includes(f) || (o.code && fold(o.code).startsWith(f)));
  }, [options, q]);
  const groups = [
    { key: "aggregate", title: "World and WHO regions", items: filtered.filter((o) => o.group === "aggregate") },
    { key: "country", title: countriesLabel, items: filtered.filter((o) => o.group === "country") },
  ].filter((g) => g.items.length);
  const flat = groups.flatMap((g) => g.items);

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const pick = (o: SeriesOption | undefined) => {
    if (!o) return;
    onAdd(o.value);
    setOpen(false);
    setQ("");
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      pick(flat[active]);
    }
  };

  const listId = "series-picker-list";
  let index = -1;
  return (
    <P.Root
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        setActive(0);
      }}
    >
      <P.Trigger
        className={cn(
          "inline-flex h-7 items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 pl-2 pr-3 text-xs font-medium text-primary",
          "outline-none transition-colors hover:border-primary/70 hover:bg-primary/15 focus-visible:ring-2 focus-visible:ring-ring/50",
          "data-[state=open]:border-primary/70 data-[state=open]:bg-primary/15",
        )}
      >
        <Plus className="size-3.5" aria-hidden />
        Add series
      </P.Trigger>
      <P.Portal>
        <P.Content
          align="start"
          sideOffset={6}
          className={cn(
            "z-50 w-80 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-xl",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          )}
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            (e.currentTarget as HTMLElement).querySelector("input")?.focus();
          }}
        >
          <div className="flex items-center gap-2 border-b border-border px-3">
            <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setActive(0);
              }}
              onKeyDown={onKey}
              placeholder="Search countries or regions…"
              aria-label="Search series"
              role="combobox"
              aria-expanded
              aria-controls={listId}
              aria-activedescendant={flat[active] ? `series-opt-${flat[active].value}` : undefined}
              className="h-10 w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div ref={listRef} id={listId} role="listbox" aria-label="Series" className="max-h-72 overflow-y-auto p-1.5">
            {groups.map((g) => (
              <div key={g.key} role="group" aria-label={g.title}>
                <div className="px-2.5 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {g.title}
                </div>
                {g.items.map((o) => {
                  index += 1;
                  const i = index;
                  return (
                    <div
                      key={o.value}
                      id={`series-opt-${o.value}`}
                      role="option"
                      aria-selected={i === active}
                      data-index={i}
                      onMouseEnter={() => setActive(i)}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => pick(o)}
                      className={cn(
                        "flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px]",
                        i === active && "bg-primary/12",
                      )}
                    >
                      <span
                        className={cn("size-2.5 shrink-0 rounded-[3px] transition-opacity", i === active ? "opacity-100" : "opacity-0")}
                        style={{ background: nextColor }}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1 truncate">
                        {o.label}
                        {o.hint && <span className="ml-1.5 text-[11px] text-muted-foreground">{o.hint}</span>}
                      </span>
                      {o.code && <span className="font-mono text-[10.5px] text-muted-foreground">{o.code}</span>}
                    </div>
                  );
                })}
              </div>
            ))}
            {flat.length === 0 && (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">No country or region matches “{q}”.</p>
            )}
          </div>
          <div className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[10.5px] text-muted-foreground">
            <span>↑↓ to move · Enter to add</span>
            <span>
              {remaining} {remaining === 1 ? "slot" : "slots"} left
            </span>
          </div>
        </P.Content>
      </P.Portal>
    </P.Root>
  );
}
