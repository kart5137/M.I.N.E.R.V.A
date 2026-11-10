import { cn } from "@/lib/utils";

const EXPANSION = "Monitoring & Intelligence Network for Epidemic Risk, Visualisation and Alerts";

/** The orbit mark: a globe with a tracked signal. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8", className)} aria-hidden>
      <defs>
        <radialGradient id="brand-core" cx="38%" cy="32%" r="75%">
          <stop offset="0" stopColor="#1a4a4c" />
          <stop offset="1" stopColor="#071c1f" />
        </radialGradient>
      </defs>
      <circle cx="16" cy="16" r="11" fill="url(#brand-core)" stroke="var(--teal)" strokeOpacity=".55" strokeWidth="1" />
      <ellipse cx="16" cy="16" rx="4.6" ry="11" fill="none" stroke="var(--teal)" strokeOpacity=".35" strokeWidth=".9" />
      <path d="M5 16h22" stroke="var(--teal)" strokeOpacity=".35" strokeWidth=".9" />
      <ellipse cx="16" cy="16" rx="15" ry="5.2" fill="none" stroke="var(--primary)" strokeWidth="1.1" transform="rotate(-24 16 16)" strokeDasharray="22 4 3 4" />
      <circle cx="25.6" cy="10.4" r="2.1" fill="var(--primary)" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("leading-none", className)} title={EXPANSION}>
      <div className="font-heading text-[15px] font-semibold tracking-[0.16em] text-foreground">M.I.N.E.R.V.A.</div>
      <div className="mt-1 text-[9.5px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
        Disease surveillance
      </div>
    </div>
  );
}

/** Mark + wordmark, used in the mobile navigation sheet. */
export function Brand() {
  return (
    <div className="flex items-center gap-3 px-4">
      <BrandMark />
      <Wordmark />
    </div>
  );
}
