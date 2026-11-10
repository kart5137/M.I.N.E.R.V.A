import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: string;
  description?: string;
  /** Small label above the title (defaults to the product name). */
  eyebrow?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 pb-1">
      <div>
        <div className="eyebrow text-teal">{eyebrow ?? "Influenza surveillance"}</div>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight lg:text-[28px]">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-[13px] text-muted-foreground">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
