"use client";

import { Check, ChevronDown } from "lucide-react";
import { Select as S } from "radix-ui";

import { rampFor } from "@/lib/disease-palette";
import { DISEASE_KEYS, DISEASES, type DiseaseInfo, type DiseaseKey } from "@/lib/diseases";
import { cn } from "@/lib/utils";

/** One line about the data behind a disease: its grain and source. */
function describe(info: DiseaseInfo): string {
  const grain = info.grain === "year" ? "Yearly" : "Weekly";
  const what = info.caseBased ? (info.grain === "year" ? "estimates and reports" : "reported cases") : "lab tests";
  return `${grain} ${what} · ${info.sourceNote}`;
}

/** The disease's colour on the globe (middle step of its ramp), as a small swatch. */
function Swatch({ disease, className }: { disease: DiseaseKey; className?: string }) {
  return (
    <span
      className={cn("inline-block size-2.5 shrink-0 rounded-full ring-1 ring-black/20", className)}
      style={{ background: rampFor(disease)[3] }}
      aria-hidden
    />
  );
}

/** The dashboard's primary switch: a listbox with each disease's colour, data grain and
 *  source, keyboard and screen-reader friendly (Radix Select). */
export function DiseaseSelect({ value, onChange }: { value: DiseaseKey; onChange: (v: DiseaseKey) => void }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span id="filter-disease-label" className="eyebrow sr-only sm:not-sr-only">
        Disease
      </span>
      <S.Root value={value} onValueChange={(v) => onChange(v as DiseaseKey)}>
        <S.Trigger
          id="filter-disease"
          aria-labelledby="filter-disease-label"
          className={cn(
            "group inline-flex h-8 min-w-36 items-center gap-2 rounded-full border border-primary/40 bg-primary/10 pl-3 pr-2.5",
            "font-medium text-primary outline-none transition-colors hover:border-primary/70 hover:bg-primary/15",
            "focus-visible:ring-2 focus-visible:ring-ring/50 data-[state=open]:border-primary/70 data-[state=open]:bg-primary/15",
          )}
        >
          <Swatch disease={value} />
          <S.Value />
          <S.Icon asChild>
            <ChevronDown
              className="ml-auto size-4 transition-transform duration-200 group-data-[state=open]:rotate-180"
              aria-hidden
            />
          </S.Icon>
        </S.Trigger>
        <S.Portal>
          <S.Content
            position="popper"
            sideOffset={6}
            align="start"
            className={cn(
              "z-50 w-80 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-xl",
              "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
            )}
          >
            <S.Viewport className="p-1.5">
              <S.Group>
                <S.Label className="px-2.5 pb-1 pt-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Choose a disease
                </S.Label>
                {DISEASE_KEYS.map((k) => {
                  const info = DISEASES[k];
                  return (
                    <S.Item
                      key={k}
                      value={k}
                      className={cn(
                        "relative flex cursor-pointer select-none items-start gap-2.5 rounded-lg py-2 pl-2.5 pr-8 outline-none",
                        "data-[highlighted]:bg-primary/12 data-[state=checked]:bg-primary/8",
                      )}
                    >
                      <Swatch disease={k} className="mt-1" />
                      <span className="flex min-w-0 flex-col">
                        <S.ItemText>
                          <span className="text-[13px] font-medium text-foreground">{info.label}</span>
                        </S.ItemText>
                        <span className="text-[11px] leading-snug text-muted-foreground">{describe(info)}</span>
                      </span>
                      <S.ItemIndicator className="absolute right-2.5 top-2.5 text-primary">
                        <Check className="size-4" aria-hidden />
                      </S.ItemIndicator>
                    </S.Item>
                  );
                })}
              </S.Group>
            </S.Viewport>
          </S.Content>
        </S.Portal>
      </S.Root>
    </div>
  );
}
