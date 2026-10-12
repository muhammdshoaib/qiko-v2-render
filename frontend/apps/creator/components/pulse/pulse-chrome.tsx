import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import type { HonestyKind } from "@/components/intelligence-layer/model";
import { cn } from "@/lib/utils";

export function PulsePage({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-full bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        {children}
      </div>
    </div>
  );
}

export type Crumb = { label: string; onClick?: () => void };

export function PulseCrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Drill path" className="mb-1.5 flex flex-wrap items-center gap-2 text-[13.5px] text-slate-500">
      {items.map((item, index) => {
        const last = index === items.length - 1;
        return (
          <span key={`${item.label}-${index}`} className="inline-flex items-center gap-2">
            {index > 0 && <ChevronRight className="size-3.5 text-slate-500" aria-hidden />}
            {last || !item.onClick ? (
              <b className="font-bold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{item.label}</b>
            ) : (
              <button
                type="button"
                onClick={item.onClick}
                className="min-h-11 text-slate-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
              >
                {item.label}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}

export function PulseHeader({
  crumbs,
  eyebrow,
  title,
  description,
  actions,
}: {
  crumbs: Crumb[];
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <PulseCrumbs items={crumbs} />
        {eyebrow && <p className="font-mono text-[11px] tracking-[0.14em] text-violet-400 uppercase">{eyebrow}</p>}
        <h1 className="mt-1 text-[26px] font-extrabold tracking-[-0.02em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
          {title}
        </h1>
        <p className="mt-1 max-w-[62ch] text-[13.5px] leading-relaxed text-slate-400">{description}</p>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function PulseCard({
  id,
  title,
  hint,
  badge,
  children,
  className,
}: {
  id?: string;
  title?: string;
  hint?: string;
  badge?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={cn("rounded-2xl border border-white/10 bg-card", className)}>
      {(title || hint || badge) && (
        <div className="flex flex-wrap items-center gap-2 px-5 pt-4">
          {title && (
            <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
              {title}
            </h2>
          )}
          {hint && <p className="text-[12px] text-slate-500">{hint}</p>}
          <span className="flex-1" />
          {badge}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function PulseChip({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: "good" | "warn" | "blue" | "bad" | "";
}) {
  const color = {
    good: "bg-emerald-400/10 text-emerald-400",
    warn: "bg-amber-400/10 text-amber-400",
    blue: "bg-cyan-400/10 text-cyan-300",
    bad: "bg-red-400/10 text-red-400",
    "": "bg-white/[0.06] text-slate-400",
  }[tone];
  return (
    <span className={cn("inline-flex items-center rounded-md px-2 py-0.5 font-mono text-[10px] tracking-[0.04em]", color)}>
      {children}
    </span>
  );
}

export function GhostButton({
  children,
  onClick,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex min-h-11 items-center rounded-lg border border-white/10 bg-white/[0.03] px-3.5 text-[13px] font-semibold text-slate-200 hover:border-white/20 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function IllustrativeMark({ kind = "illustrative" }: { kind?: HonestyKind }) {
  return <HonestyBadge kind={kind} />;
}
