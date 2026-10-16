"use client";

import type { ReactNode } from "react";
import { Button, cn } from "@qiko/ui";
import type { ShowcaseOutcome } from "@/lib/studio/showcase";
import type { FocusId } from "@/components/intelligence-layer/model";

export type FeedLead = {
  title: string;
  detail: string;
  at: string;
  originLabel: string;
  status: "attention" | "completed";
  onOpen: () => void;
  actions?: ReactNode;
};

export function PulseFeed({
  attention,
  recent,
  leadAttention,
  leadRecent,
  onOpen,
  onApprove,
  onHold,
}: {
  attention: ShowcaseOutcome[];
  recent: ShowcaseOutcome[];
  leadAttention?: FeedLead | null;
  leadRecent?: FeedLead | null;
  onOpen: (id: FocusId) => void;
  onApprove?: () => void;
  onHold?: () => void;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <FeedCard
        title="Needs your attention"
        empty="Nothing waiting on you."
        items={attention}
        lead={leadAttention}
        onOpen={onOpen}
        onApprove={onApprove}
        onHold={onHold}
      />
      <FeedCard title="Recent activity" empty="No recent actions." items={recent} lead={leadRecent} onOpen={onOpen} />
    </div>
  );
}

function FeedCard({
  title,
  empty,
  items,
  lead,
  onOpen,
  onApprove,
  onHold,
}: {
  title: string;
  empty: string;
  items: ShowcaseOutcome[];
  lead?: FeedLead | null;
  onOpen: (id: FocusId) => void;
  onApprove?: () => void;
  onHold?: () => void;
}) {
  const vacant = items.length === 0 && !lead;
  return (
    <section className="rounded-2xl border border-border bg-card p-5" aria-label={title}>
      <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>{title}</h2>
      {vacant ? (
        <p className="mt-4 text-sm text-slate-400">{empty}</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {lead && (
            <li className="py-3 first:pt-1">
              <button
                type="button"
                onClick={lead.onOpen}
                className="w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-[13.5px] font-medium text-foreground">{lead.title}</p>
                  <span className={cn("shrink-0 font-mono text-[10.5px] uppercase tracking-wider", lead.status === "attention" ? "text-amber-700" : "text-slate-400")}>
                    {lead.status === "attention" ? "Review" : "Done"}
                  </span>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-slate-600">{lead.detail}</p>
                <p className="mt-2 font-mono text-[11px] text-slate-400">{lead.originLabel} · {lead.at}</p>
              </button>
              {lead.actions}
            </li>
          )}
          {items.map((item) => (
            <li key={item.title} className="py-3 first:pt-1">
              <button
                type="button"
                onClick={() => onOpen(item.origin)}
                className="w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-[13.5px] font-medium text-foreground">{item.title}</p>
                  <span className={cn("shrink-0 font-mono text-[10.5px] uppercase tracking-wider", item.status === "attention" ? "text-amber-700" : "text-slate-400")}>
                    {item.status === "attention" ? "Review" : "Done"}
                  </span>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-slate-600">{item.detail}</p>
                <p className="mt-2 font-mono text-[11px] text-slate-400">
                  {item.originLabel} · {item.at}
                </p>
              </button>
              {item.status === "attention" && onApprove && onHold && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Button type="button" size="sm" onClick={onApprove}>Approve review</Button>
                  <Button type="button" size="sm" variant="outline" onClick={onHold}>Hold</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
