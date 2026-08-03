"use client";

// Pre-Sales / RFP Writer worker (atype="pre_sales_writer"). One route drives two surfaces off the
// ?pack= URL param: with NO ?pack= we show the worker LANDING (use-case rail: AI Response
// Generation, Knowledge Base, Section Assignment); with ?pack=<id> we open the full-screen dark,
// tab-driven cockpit for that tender (Overview/Sources/Brief/Sections/Compliance/Export), backed by
// the /rfp/packs/{id} section->question tree API. The URL is the source of truth, so opening an RFP
// card (router.push ?pack) and going Back (clear ?pack) are plain navigations.
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { listAgents, listRfpPacks, type RfpPack } from "@/lib/api";
import { PreSalesCockpitShell, type PreSalesTab } from "@/components/pre-sales/cockpit-shell";
import { OverviewTab } from "@/components/pre-sales/overview-tab";
import { SourcesTab } from "@/components/pre-sales/sources-tab";
import { BriefTab } from "@/components/pre-sales/brief-tab";
import { SectionsTab } from "@/components/pre-sales/sections-tab";
import { ComplianceTab } from "@/components/pre-sales/compliance-tab";
import { ExportTab } from "@/components/pre-sales/export-tab";
import { WorkerLanding } from "@/components/pre-sales/worker-landing";
import { NewTenderPanel } from "@/components/pre-sales/new-tender-panel";

export default function PreSalesCockpitPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  // The ?pack= param is the source of truth: absent -> worker landing; present -> that tender's cockpit.
  const requestedPackId = searchParams.get("pack");
  const [tab, setTab] = useState<PreSalesTab>("overview");
  const [showNew, setShowNew] = useState(false);

  const agentsQ = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agentsQ.data?.find((a) => a.id === agentId);

  const packsQ = useQuery({ queryKey: ["rfp-packs", agentId], queryFn: () => listRfpPacks(agentId) });
  const packs = useMemo<RfpPack[]>(() => packsQ.data ?? [], [packsQ.data]);

  // If this worker isn't a pre-sales vertical, hand it back to the boilerplate router.
  useEffect(() => {
    if (worker && worker.atype !== "pre_sales_writer") router.replace(`/studio/${agentId}`);
  }, [worker, agentId, router]);

  const workerName = worker?.name ?? "Pre-Sales / RFP Writer";
  const goToPack = (packId: string) => router.push(`/studio/${agentId}/pre-sales?pack=${packId}`);
  const backToLanding = () => router.push(`/studio/${agentId}/pre-sales`);

  // ---- Loading ---------------------------------------------------------------
  if (agentsQ.isLoading || packsQ.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#05070d] text-slate-400">
        <Loader2 className="size-5 animate-spin" /> <span className="ml-2 text-sm">Loading{"\u2026"}</span>
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

  // ---- Worker landing (no ?pack=) --------------------------------------------
  if (!requestedPackId) {
    return (
      <WorkerLanding
        agentId={agentId}
        workerName={workerName}
        packs={packs}
        onOpenPack={goToPack}
      />
    );
  }

  // ---- Cockpit (?pack=<id>) --------------------------------------------------
  const activePack = packs.find((p) => p.id === requestedPackId) ?? null;

  return (
    <PreSalesCockpitShell
      workerName={workerName}
      active={tab}
      onSelect={setTab}
      packs={packs}
      activePackId={requestedPackId}
      onSelectPack={(id) => { setShowNew(false); goToPack(id); }}
      activePack={activePack}
      onNewTender={() => setShowNew(true)}
      onBack={backToLanding}
    >
      {showNew ? (
        <NewTenderPanel
          agentId={agentId}
          onCreated={(packId) => { setShowNew(false); setTab("overview"); goToPack(packId); }}
          onCancel={() => setShowNew(false)}
        />
      ) : !activePack ? (
        <p className="text-sm text-slate-500">Select a tender to begin.</p>
      ) : tab === "overview" ? (
        <OverviewTab packId={requestedPackId} onOpenSections={() => setTab("sections")} onOpenBrief={() => setTab("brief")} />
      ) : tab === "sources" ? (
        <SourcesTab agentId={agentId} />
      ) : tab === "brief" ? (
        <BriefTab packId={requestedPackId} onOpenSources={() => setTab("sources")} />
      ) : tab === "sections" ? (
        <SectionsTab packId={requestedPackId} />
      ) : tab === "compliance" ? (
        <ComplianceTab packId={requestedPackId} onOpenSources={() => setTab("sources")} />
      ) : (
        <ExportTab packId={requestedPackId} />
      )}
    </PreSalesCockpitShell>
  );
}
