"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Search } from "lucide-react";
import { Button, Input, cn } from "@qiko/ui";
import { OWNERS } from "@/lib/crm/seed";
import { formatMoney, isStalled, timeSince } from "@/lib/crm/format";
import { useCrm } from "@/lib/crm/store";
import { PIPELINE_STAGES, STAGE_LABEL, type Opportunity, type PipelineStage } from "@/lib/crm/types";
import { OpportunityDialog } from "./opportunity-dialog";
import { PrototypeBadge } from "./prototype-badge";

export function CrmPipelinePage() {
  const crm = useCrm();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [owner, setOwner] = useState("all");
  const [stalledOnly, setStalledOnly] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [editing, setEditing] = useState<Opportunity | null>(null);
  const [creating, setCreating] = useState(false);

  const items = useMemo(() => crm.opportunities.filter((opp) => {
    const company = crm.companyById(opp.companyId);
    const haystack = `${company?.name ?? ""} ${opp.title} ${opp.owner}`.toLowerCase();
    if (query && !haystack.includes(query.toLowerCase())) return false;
    if (owner !== "all" && opp.owner !== owner) return false;
    if (stalledOnly && !isStalled(opp.lastActivityAt, opp.stage)) return false;
    return true;
  }), [crm, owner, query, stalledOnly]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter companies or owners" className="pl-9" />
          </div>
          <select value={owner} onChange={(event) => setOwner(event.target.value)} className="h-11 rounded-md border border-input bg-background px-3 text-sm">
            <option value="all">All owners</option>
            {OWNERS.map((name) => <option key={name}>{name}</option>)}
          </select>
          <Button type="button" variant={stalledOnly ? "secondary" : "outline"} onClick={() => setStalledOnly((value) => !value)}>
            Stalled only
          </Button>
        </div>
        <Button type="button" onClick={() => setCreating(true)}><Plus className="size-4" /> New opportunity</Button>
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border px-6 py-16 text-center">
          <p className="text-sm text-foreground">No opportunities match these filters.</p>
          <p className="mt-1 text-sm text-slate-400">Clear filters or create a new record.</p>
        </div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-4">
          {PIPELINE_STAGES.map((stage) => {
            const column = items.filter((item) => item.stage === stage);
            return (
              <section
                key={stage}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => {
                  if (dragging) crm.moveOpportunity(dragging, stage);
                  setDragging(null);
                }}
                className="flex w-72 shrink-0 flex-col rounded-2xl border border-border bg-muted/40"
              >
                <header className="flex items-center justify-between px-3 py-3">
                  <h2 className="text-sm font-semibold text-foreground">{STAGE_LABEL[stage]}</h2>
                  <span className="text-xs tabular-nums text-slate-500">{column.length}</span>
                </header>
                <div className="flex min-h-24 flex-col gap-2 px-2 pb-3">
                  {column.map((opp) => {
                    const company = crm.companyById(opp.companyId);
                    const stalled = isStalled(opp.lastActivityAt, opp.stage);
                    const suggestion = crm.suggestions.find((item) => item.opportunityId === opp.id && !item.applied);
                    return (
                      <article
                        key={opp.id}
                        draggable
                        onDragStart={() => setDragging(opp.id)}
                        onDragEnd={() => setDragging(null)}
                        className={cn(
                          "cursor-grab rounded-xl border bg-card p-3 active:cursor-grabbing",
                          stalled ? "border-amber-500/30" : "border-border",
                          dragging === opp.id && "opacity-60",
                        )}
                      >
                        <button type="button" className="w-full text-left" onClick={() => router.push(`/crm/companies/${opp.companyId}`)}>
                          <p className="text-sm font-medium text-foreground">{company?.name}</p>
                          <p className="text-xs text-slate-400">{opp.title}</p>
                        </button>
                        <p className="mt-2 text-sm text-slate-700">{formatMoney(opp.value)}</p>
                        <p className="mt-1 text-xs text-slate-500">{opp.owner} · {timeSince(opp.lastActivityAt)}</p>
                        <p className="mt-2 text-xs text-slate-600">Next: {opp.nextStep}</p>
                        {stalled && <p className="mt-2 text-xs text-amber-300">Stalled · no activity for 7+ days</p>}
                        {suggestion && (
                          <p className="mt-2 flex items-start gap-2 text-xs text-indigo-200">
                            <PrototypeBadge label="Agent" tone="default" />
                            <span>{suggestion.message}</span>
                          </p>
                        )}
                        <div className="mt-3 flex gap-2">
                          <Link href={`/crm/companies/${opp.companyId}`} className="text-xs text-indigo-600 hover:underline">Open</Link>
                          <button type="button" className="text-xs text-slate-500 hover:text-foreground" onClick={() => setEditing(opp)}>Edit</button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      )}

      <OpportunityDialog key={creating ? "new" : "closed-new"} open={creating} onOpenChange={setCreating} />
      {editing && (
        <OpportunityDialog key={editing.id} open onOpenChange={(open) => !open && setEditing(null)} initial={editing} />
      )}
    </div>
  );
}
