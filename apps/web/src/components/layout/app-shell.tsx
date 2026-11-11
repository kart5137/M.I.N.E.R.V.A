"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { type ReactNode, Suspense, useState } from "react";

import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

import { Brand, BrandMark, Wordmark } from "./brand";
import { DataStatus } from "./data-status";
import { HomeLink } from "./home-link";
import { FilterBar } from "./filter-bar";
import { NavRail, SidebarNav } from "./sidebar-nav";
import { WakeNotice } from "./wake-notice";

const DISCLAIMER = "Analytical tool. Not medical advice or official public-health guidance.";

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-xs focus:font-medium focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <aside
        aria-label="Sidebar"
        className="sticky top-0 hidden h-dvh w-[72px] shrink-0 flex-col items-center gap-6 border-r border-sidebar-border bg-sidebar/95 py-4 lg:flex"
      >
        <Suspense
          fallback={
            <Link href="/" aria-label="M.I.N.E.R.V.A. home" className="rounded-xl p-1">
              <BrandMark className="size-9" />
            </Link>
          }
        >
          <HomeLink className="rounded-xl p-1 transition-transform hover:scale-105">
            <BrandMark className="size-9" />
          </HomeLink>
        </Suspense>
        {/* usePathname needs a Suspense boundary under Cache Components. */}
        <Suspense fallback={null}>
          <NavRail />
        </Suspense>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex min-h-16 flex-wrap items-center gap-x-4 gap-y-2 border-b border-border/70 bg-background/80 px-4 py-2.5 backdrop-blur-md lg:px-6">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                className="-ml-1 rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden"
                aria-label="Open navigation"
              >
                <Menu className="size-5" />
              </button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 border-sidebar-border bg-sidebar p-0">
              <SheetTitle className="sr-only">Navigation</SheetTitle>
              <div className="flex h-full flex-col gap-6 py-5">
                <Brand />
                <Suspense fallback={null}>
                  <SidebarNav onNavigate={() => setMobileOpen(false)} />
                </Suspense>
                <p className="mt-auto px-5 text-[10.5px] leading-relaxed text-subtle-foreground">{DISCLAIMER}</p>
              </div>
            </SheetContent>
          </Sheet>

          {/* The logo and name lead home (the Overview), keeping the selected disease. */}
          <Suspense
            fallback={
              <Link href="/" aria-label="M.I.N.E.R.V.A. home" className="flex items-center">
                <BrandMark className="size-7 sm:hidden" />
                <Wordmark className="hidden sm:block" />
              </Link>
            }
          >
            <HomeLink className="flex items-center rounded-md transition-opacity hover:opacity-85">
              <BrandMark className="size-7 sm:hidden" />
              <Wordmark className="hidden sm:block" />
            </HomeLink>
          </Suspense>
          <span className="hidden h-7 w-px bg-border sm:block" aria-hidden />

          {/* Phones: disease and filters take their own row under the menu, logo and status. */}
          <div className="order-last w-full sm:order-none sm:w-auto">
            {/* useSearchParams needs a Suspense boundary under Cache Components. */}
            <Suspense fallback={null}>
              <FilterBar />
            </Suspense>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <DataStatus />
          </div>
        </header>

        <main id="main" tabIndex={-1} className="flex min-w-0 flex-1 flex-col outline-none">
          {children}
        </main>
        <footer className="border-t border-border/60 px-4 py-2.5 text-[10.5px] text-subtle-foreground lg:px-6">
          {DISCLAIMER}
        </footer>
      </div>
      <WakeNotice />
    </div>
  );
}
