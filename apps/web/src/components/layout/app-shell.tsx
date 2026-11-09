"use client";

import { Menu } from "lucide-react";
import { type ReactNode, Suspense, useState } from "react";

import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

import { Brand } from "./brand";
import { DataStatus } from "./data-status";
import { FilterBar } from "./filter-bar";
import { SidebarNav } from "./sidebar-nav";

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-6 py-4">
      <Brand />
      {/* usePathname needs a Suspense boundary under Cache Components. */}
      <Suspense fallback={null}>
        <SidebarNav onNavigate={onNavigate} />
      </Suspense>
      <p className="mt-auto px-4 text-[10.5px] leading-relaxed text-subtle-foreground">
        Analytical tool. Not medical advice or official public-health guidance.
      </p>
    </div>
  );
}

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
        className="sticky top-0 hidden h-dvh w-60 shrink-0 border-r border-sidebar-border bg-sidebar lg:block"
      >
        <SidebarBody />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex min-h-14 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border bg-background/85 px-4 py-2 backdrop-blur lg:px-6">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                className="-ml-1 rounded-md p-1.5 text-muted-foreground hover:text-foreground lg:hidden"
                aria-label="Open navigation"
              >
                <Menu className="size-5" />
              </button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 border-sidebar-border bg-sidebar p-0">
              <SheetTitle className="sr-only">Navigation</SheetTitle>
              <SidebarBody onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>

          <div className="hidden items-center gap-2 text-xs sm:flex">
            <span className="text-muted-foreground">Disease</span>
            <span className="rounded-md border border-border bg-card px-2 py-1 font-medium">
              Influenza
            </span>
          </div>

          {/* useSearchParams needs a Suspense boundary under Cache Components. */}
          <Suspense fallback={null}>
            <FilterBar />
          </Suspense>

          <div className="ml-auto flex items-center gap-2">
            <DataStatus />
          </div>
        </header>

        <main id="main" tabIndex={-1} className="flex min-w-0 flex-1 flex-col outline-none">
          {children}
        </main>
      </div>
    </div>
  );
}
