"use client";

// Pre-Sales / RFP Writer cockpit (atype="pre_sales_writer"). A full-screen, dark, tab-driven
// cockpit -- mirrors the Sales Intelligence cockpit for cross-vertical consistency -- backed by the
// /rfp/packs/{id} section->question tree API. One route (this page) owns tab + active-tender state;
// section detail is a view within the Sections tab, not a separate route.
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText, Loader2 } from "lucide-react";
import { listAgents, listRfpPacks, type RfpPack } from "@/lib/api";
import { PreSalesCockpitShell, type PreSalesTab } from "@/components/pre-sales/cockpit-shell";
import { OverviewTab } from "@/components/pre-sales/overview-tab";
import { SourcesTab } from "@/components/pre-sales/sources-tab";
import { BriefTab } from "@/components/pre-sales/brief-tab";
import { SectionsTab } from "@/components/pre-sales/sections-tab";
import { ComplianceTab } from "@/components/pre-sales/compliance-tab";
import { ExportTab } from "@/components/pre-sales/export-tab";
import { TendersListView } from "@/components/pre-sales/tenders-list";
import { NewTenderPanel } from "@/components/pre-sales/new-tender-panel";

export default function PreSalesCockpitPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  // Deep-link support: /studio/[id]/pre-sales?pack=<packId> (e.g. from the Worker Overview
  // "Tenders" list) opens the cockpit with that tender preselected.
  const requestedPackId = searchParams.get("pack");
  // With no ?pack= deep-link, land on the "Tenders" overview list (all tenders for this worker) so
  // the user picks one to drill into; a deep-link jumps straight into that tender's Overview.
  const [tab, setTab] = useState<PreSalesTab>(requestedPackId ? "overview" : "tenders");
  const [activePackId, setActivePackId] = useState<string | null>(requestedPackId);
  const [showNew, setShowNew] = useState(false);

  const agentsQ = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agentsQ.data?.find((a) => a.id === agentId);

  const packsQ = useQuery({ queryKey: ["rfp-packs", agentId], queryFn: () => listRfpPacks(agentId) });
  const packs = useMemo<RfpPack[]>(() => packsQ.data ?? [], [packsQ.data]);

  // If this worker isn't a pre-sales vertical, hand it back to the boilerplate router.
  useEffect(() => {
    if (worker && worker.atype !== "pre_sales_writer") router.replace(`/studio/${agentId}`);
  }, [worker, agentId, router]);

  // Default the active tender to the first pack once they load; keep the current one if still present.
  // A ?pack= deep-link (from the Worker Overview "Tenders" list) is honoured once when it resolves
  // -- useSearchParams() can be null on the first render, so seeding it only in useState would race
  // with this effect and fall back to packs[0]. After that first honour the user can switch freely.
  const deepLinkHonoured = useRef(false);
  useEffect(() => {
    if (packs.length === 0) { setActivePackId(null); deepLinkHonoured.current = false; return; }
    setActivePackId((cur) => {
      if (!deepLinkHonoured.current && requestedPackId && packs.some((p) => p.id === requestedPackId)) {
        deepLinkHonoured.current = true;
        return requestedPackId;
      }
      return cur && packs.some((p) => p.id === cur) ? cur : packs[0].id;
    });
  }, [packs, requestedPackId]);

  const workerName = worker?.name ?? "Pre-Sales / RFP Writer";
  const activePack = packs.find((p) => p.id === activePackId) ?? null;

  // ---- Loading ---------------------------------------------------------------
  if (agentsQ.isLoading || packsQ.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#05070d] text-slate-400">
        <Loader2 className="size-5 animate-spin" /> <span className="ml-2 text-sm">Loading cockpit{"\u2026"}</span>
      </div>
    );
  }

  // ---- Error -----------------------------------------------------------------
  if (packsQ.isError) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-[#05070d] text-slate-300">
        <p className="text-sm">Couldn&apos;t load tenders for this worker.</p>
        <button onClick={() => packsQ.refetch()} className="rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-2 text-[13px] font-semibold hover:bg-white/[0.06]">
          Try again
        </button>
      </div>
    );
  }

  // ---- Empty state: no tenders yet -------------------------------------------
  if (packs.length === 0) {
    return (
      <div className="flex h-screen flex-col bg-[#05070d] text-slate-200">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-white/[0.06] px-4">
          <button onClick={() => router.push("/studio")} className="flex items-center gap-1.5 rounded-md px-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
            <ArrowLeft className="size-4" /> Studio
          </button>
          <span className="h-4 w-px bg-white/10" />
          <span className="flex size-6 items-center justify-center rounded-md bg-indigo-500/15 text-indigo-400"><FileText className="size-3.5" /></span>
          <h1 className="truncate text-sm font-semibold text-white">{workerName}</h1>
        </header>
        <main className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10">
          <div className="mb-6 text-center">
            <h2 className="text-lg font-semibold text-white">No tenders yet</h2>
            <p className="mt-1 text-[13px] text-slate-500">Upload your first RFP to start drafting a grounded response.</p>
          </div>
          <NewTenderPanel agentId={agentId} onCreated={(packId) => { setActivePackId(packId); setTab("overview"); }} />
        </main>
      </div>
    );
  }

  // ---- Cockpit ---------------------------------------------------------------
  return (
    <PreSalesCockpitShell
      workerName={workerName}
      active={tab}
      onSelect={setTab}
      packs={packs}
      activePackId={activePackId}
      onSelectPack={(id) => { setActivePackId(id); setShowNew(false); }}
      activePack={activePack}
      onNewTender={() => setShowNew(true)}
    >
      {showNew ? (
        <NewTenderPanel
          agentId={agentId}
          onCreated={(packId) => { setActivePackId(packId); setShowNew(false); setTab("overview"); }}
          onCancel={() => setShowNew(false)}
        />
      ) : tab === "tenders" ? (
        <TendersListView
          packs={packs}
          onOpen={(id) => { setActivePackId(id); setShowNew(false); setTab("overview"); }}
          onNewTender={() => setShowNew(true)}
        />
      ) : !activePackId ? (
        <p className="text-sm text-slate-500">Select a tender to begin.</p>
      ) : tab === "overview" ? (
        <OverviewTab packId={activePackId} onOpenSections={() => setTab("sections")} onOpenBrief={() => setTab("brief")} />
      ) : tab === "sources" ? (
        <SourcesTab />
      ) : tab === "brief" ? (
        <BriefTab packId={activePackId} onOpenSources={() => setTab("sources")} />
      ) : tab === "sections" ? (
        <SectionsTab packId={activePackId} />
      ) : tab === "compliance" ? (
        <ComplianceTab packId={activePackId} onOpenSources={() => setTab("sources")} />
      ) : (
        <ExportTab packId={activePackId} />
      )}
    </PreSalesCockpitShell>
  );
}
