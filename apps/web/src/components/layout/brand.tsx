export function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-4">
      <svg viewBox="0 0 24 24" className="size-6 text-primary" aria-hidden>
        <circle cx="12" cy="12" r="9.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <ellipse cx="12" cy="12" rx="4" ry="9.25" fill="none" stroke="currentColor" strokeWidth="1" opacity=".55" />
        <path d="M2.75 12h18.5" stroke="currentColor" strokeWidth="1" opacity=".55" />
        <circle cx="15.5" cy="8.5" r="2" fill="currentColor" />
      </svg>
      <div className="leading-tight">
        <div className="text-[13px] font-semibold tracking-tight text-foreground">
          Epidemic Intelligence
        </div>
        <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted-foreground">
          Global surveillance
        </div>
      </div>
    </div>
  );
}
