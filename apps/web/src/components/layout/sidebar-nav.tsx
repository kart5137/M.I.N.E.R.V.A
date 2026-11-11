"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { diseaseParam, useFilters, withParams } from "@/lib/filters";
import { cn } from "@/lib/utils";

import { NAV_ITEMS } from "./nav-items";

/** Nav links keep the selected disease, so moving between pages does not reset it. */
function useHref() {
  const [filters] = useFilters();
  const q = diseaseParam(filters.disease);
  return (href: string) => withParams(href, q);
}

function useIsActive() {
  const pathname = usePathname();
  return (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
}

/** Desktop: a slim icon rail; each item names itself in a tooltip and to screen readers. */
export function NavRail() {
  const isActive = useIsActive();
  const toHref = useHref();
  return (
    <nav aria-label="Main" className="flex flex-col items-center gap-1.5">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = isActive(item.href);
        return (
          <Tooltip key={item.href}>
            <TooltipTrigger asChild>
              <Link
                href={toHref(item.href)}
                aria-label={item.label}
                aria-current={active ? "page" : undefined}
                className={cn(
                  // Hover: the tile lifts and glows in the accent colour (motion only when the
                  // user has not asked for reduced motion).
                  "group relative grid size-11 place-items-center rounded-xl outline-none transition-[background-color,color,box-shadow,transform] duration-200 ease-out",
                  "focus-visible:ring-2 focus-visible:ring-ring/60",
                  "hover:bg-primary/15 hover:text-primary hover:shadow-[0_0_0_1px_color-mix(in_oklab,var(--primary)_40%,transparent),0_6px_18px_-4px_color-mix(in_oklab,var(--primary)_45%,transparent)] motion-safe:hover:scale-110",
                  active ? "bg-primary/12 text-primary" : "text-sidebar-foreground",
                )}
              >
                {active && (
                  <span className="absolute -left-3.5 top-2 h-7 w-1 rounded-r-full bg-primary" aria-hidden />
                )}
                <Icon
                  className="size-[19px] transition-transform duration-200 ease-out motion-safe:group-hover:scale-110"
                  strokeWidth={active ? 2.1 : 1.8}
                  aria-hidden
                />
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={10}>
              {item.label}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </nav>
  );
}

/** Mobile sheet: full labels. */
export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const isActive = useIsActive();
  const toHref = useHref();
  return (
    <nav aria-label="Main" className="flex flex-col gap-1 px-3">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={toHref(item.href)}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group flex h-10 items-center gap-3 rounded-lg px-3 text-[13.5px] font-medium transition-colors",
              active ? "bg-primary/12 text-primary" : "text-sidebar-foreground hover:bg-primary/12 hover:text-primary",
            )}
          >
            <Icon
              className="size-[18px] shrink-0 transition-transform duration-200 motion-safe:group-hover:scale-110"
              aria-hidden
            />
            <span className="truncate">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
