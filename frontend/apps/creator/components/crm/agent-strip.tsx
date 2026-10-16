"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";
import { Button } from "@qiko/ui";
import { toast } from "sonner";
import { useCrm } from "@/lib/crm/store";
import { PrototypeBadge } from "./prototype-badge";

export function AgentStrip({ companyId }: { companyId?: string }) {
  const crm = useCrm();
  const items = crm.suggestions.filter((item) => !item.applied && (!companyId || item.companyId === companyId));

  if (items.length === 0) {
    return (
      <section className="rounded-2xl border border-border bg-muted/40 p-4">
        <p className="flex items-center gap-2 text-sm text-slate-400">
          <Sparkles className="size-4 text-indigo-600" />
          No open agent suggestions.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="agent-strip-title" className="rounded-2xl border border-indigo-500/20 bg-indigo-500/[0.06] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 id="agent-strip-title" className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Sparkles className="size-4 text-indigo-600" />
          Agent suggestions
        </h2>
        <PrototypeBadge label="Agent · mock" />
      </div>
      <ul className="space-y-2">
        {items.map((item) => {
          const company = crm.companyById(item.companyId);
          return (
            <li key={item.id} className="flex flex-col gap-2 rounded-xl border border-border bg-background/60 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm text-foreground">{item.message}</p>
                <p className="text-xs text-slate-400">
                  {company ? <Link href={`/crm/companies/${company.id}`} className="hover:underline">{company.name}</Link> : "Unknown company"}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                onClick={() => toast.message(crm.applySuggestion(item.id))}
              >
                {item.actionLabel}
              </Button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
