"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Layers, Loader2, RadioTower, RefreshCw, Search, Sparkles } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  listAgents, listSalesOpportunities, listSalesSources, scanTedSource, scanUngmSource, updateSalesSource,
  type SalesIntelSource, type SalesScanCadence,
} from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OutcomesStrip } from "@/components/sales-intelligence/outcomes-strip";
import { Input, Switch } from "@/components/cockpit/controls";
import { formatDate, humanize } from "@/components/sales-intelligence/utils";

// Per-source scheduled scan cadence options (mirrors Ali's SCAN_CADENCE_OPTIONS).
const SCAN_CADENCE_OPTIONS: { value: SalesScanCadence; label: string }[] = [
  { value: "minutely", label: "Per minute" },
  { value: "hourly", label: "Per hour" },
  { value: "daily", label: "Per day" },
  { value: "weekly", label: "Per week" },
  { value: "manual", label: "Manual only" },
];

// Coerce a stored cadence (which may be a legacy "every_N_minutes" value) to a select option.
function cadenceValue(cadence: string | null | undefined): SalesScanCadence {
  return SCAN_CADENCE_OPTIONS.some((o) => o.value === cadence) ? (cadence as SalesScanCadence) : "minutely";
}

// Tone colour for a source's last-scan status string (>= 4.5:1 on the dark card).
function scanStatusClass(status: string | null | undefined): string {
  const s = (status || "").toLowerCase();
  if (s.includes("fail") || s.includes("error")) return "text-red-400";
  if (s.includes("success") || s.includes("complete") || s.includes("ok")) return "text-emerald-400";
  if (!s) return "text-slate-500";
  return "text-slate-300";
}

export default function SalesIntelligenceIngestionPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [query, setQuery] = useState("security");
  const [useQuery_, setUseQuery] = useState(true);
  const [allCountries, setAllCountries] = useState(false);
  const [allCategories, setAllCategories] = useState(false);

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const sourcesQ = useQuery({ queryKey: ["sales-sources", agentId], queryFn: () => listSalesSources(agentId), retry: false });
  const sources: SalesIntelSource[] = sourcesQ.data?.sources ?? [];

  const oppsQ = useQuery({ queryKey: ["sales-opportunities", agentId], queryFn: () => listSalesOpportunities(agentId, { limit: "all" }), retry: false });
  const opps = oppsQ.data?.opportunities ?? [];

  // Scan payload: the keyword (when enabled) plus the two allowlist-bypass toggles, so the
  // "All countries" / "All categories" switches actually reach the portal scan instead of being
  // inert local state.
  const scanBody = () => ({
    query: useQuery_ ? query : undefined,
    all_countries: allCountries,
    all_categories: allCategories,
  });
  const scanTed = useMutation({
    mutationFn: () => scanTedSource(agentId, scanBody()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["sales-sources", agentId] }); qc.invalidateQueries({ queryKey: ["sales-opportunities", agentId] }); },
  });
  const scanUngm = useMutation({
    mutationFn: () => scanUngmSource(agentId, scanBody()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["sales-sources", agentId] }); qc.invalidateQueries({ queryKey: ["sales-opportunities", agentId] }); },
  });

  // Per-source scan-cadence change. Tracks the in-flight source key so only that card shows a
  // loading state while the mutation settles.
  const cadenceMut = useMutation({
    mutationFn: ({ sourceKey, cadence }: { sourceKey: "ted" | "ungm"; cadence: SalesScanCadence }) =>
      updateSalesSource(agentId, sourceKey, { scan_cadence: cadence }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales-sources", agentId] }),
  });
  const updatingCadenceKey = cadenceMut.isPending ? cadenceMut.variables?.sourceKey : null;

  // Per-source enable/disable. Sends the documented "active"/"inactive" status; the backend
  // rejects scans of an inactive source, so this is the on/off switch for scheduled ingestion.
  const statusMut = useMutation({
    mutationFn: ({ sourceKey, active }: { sourceKey: "ted" | "ungm"; active: boolean }) =>
      updateSalesSource(agentId, sourceKey, { status: active ? "active" : "inactive" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales-sources", agentId] }),
  });
  const updatingStatusKey = statusMut.isPending ? statusMut.variables?.sourceKey : null;

  const activeSources = sources.filter((s) => s.status === "active").length;
  const newFromLastScan = useMemo(() => opps.filter((o) => o.stage === "ingested").length, [opps]);

  const ted = sources.find((s) => s.sourceKey === "ted");
  const ungm = sources.find((s) => s.sourceKey === "ungm");

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="ingestion">
      <div className="space-y-6">
        <OutcomesStrip title="INGESTION" tiles={[
          { value: String(activeSources), label: "Active Sources", caption: "UNGM \u00b7 TED portals", trend: "up" },
          { value: String(opps.length), label: "Opportunities Ingested", caption: "all time", trend: "up" },
          { value: String(newFromLastScan), label: "New from Last Scan", caption: "ready to qualify", trend: "up" },
        ]} />

        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-[15px] font-semibold text-white">Portal ingestion</h2>
              <p className="mt-1 max-w-2xl text-[13px] text-slate-400">
                Pull tenders from active portals, apply IDG country and category filters, then stage matches as{" "}
                <span className="font-semibold text-slate-200">Ingested</span> for qualification.
              </p>
            </div>
            <div className="shrink-0 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-2.5 text-center">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Active Sources</p>
              <p className="mt-0.5 text-[15px] font-bold text-white">{activeSources} / {sources.length || 2}</p>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <SourceCard icon={<Layers className="size-5" />} name="TED - EU Tenders" sourceKey="TED" fullName="EU Tenders Electronic Daily"
              source={ted} onScan={() => scanTed.mutate()} scanning={scanTed.isPending} error={scanTed.isError}
              onCadenceChange={(cadence) => cadenceMut.mutate({ sourceKey: "ted", cadence })} cadenceUpdating={updatingCadenceKey === "ted"}
              onToggleActive={(active) => statusMut.mutate({ sourceKey: "ted", active })} statusUpdating={updatingStatusKey === "ted"} />
            <SourceCard icon={<RadioTower className="size-5" />} name="UNGM Public Notices" sourceKey="UNGM" fullName="UN Global Marketplace"
              source={ungm} onScan={() => scanUngm.mutate()} scanning={scanUngm.isPending} error={scanUngm.isError}
              onCadenceChange={(cadence) => cadenceMut.mutate({ sourceKey: "ungm", cadence })} cadenceUpdating={updatingCadenceKey === "ungm"}
              onToggleActive={(active) => statusMut.mutate({ sourceKey: "ungm", active })} statusUpdating={updatingStatusKey === "ungm"} />
          </div>
        </div>

        <div>
          <p className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
            <Sparkles className="size-3.5" /> INGEST FILTERS
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <FilterCard icon={<Search className="size-4" />} title="Portal query"
              description="Keyword for TED notice titles and UNGM descriptions. Toggle off for an open portal search."
              enabled={useQuery_} onToggle={() => setUseQuery((v) => !v)}
              helper={useQuery_ ? "Keyword search" : "Open search (no keyword)"}>
              <Input value={query} onChange={(e) => setQuery(e.target.value)} disabled={!useQuery_}
                placeholder="security" aria-label="Portal query keyword" className="mt-3" />
            </FilterCard>
            <FilterCard icon={<Layers className="size-4" />} title="All countries"
              description="Bypass the 14-country IDG target allowlist after the portal returns notices."
              enabled={allCountries} onToggle={() => setAllCountries((v) => !v)}
              helper={allCountries ? "Bypassing allowlist" : "Using configured allowlist"} />
            <FilterCard icon={<Layers className="size-4" />} title="All categories"
              description="Bypass security category aliases from config (guard services, UNRWA wording, etc.)."
              enabled={allCategories} onToggle={() => setAllCategories((v) => !v)}
              helper={allCategories ? "Bypassing category aliases" : "Using configured allowlist"} />
          </div>
        </div>
      </div>
    </CockpitShell>
  );
}

function SourceCard({ icon, name, sourceKey, fullName, source, onScan, scanning, error, onCadenceChange, cadenceUpdating, onToggleActive, statusUpdating }: {
  icon: React.ReactNode; name: string; sourceKey: string; fullName: string;
  source?: SalesIntelSource; onScan: () => void; scanning: boolean; error?: boolean;
  onCadenceChange: (cadence: SalesScanCadence) => void; cadenceUpdating: boolean;
  onToggleActive: (active: boolean) => void; statusUpdating: boolean;
}) {
  const active = (source?.status ?? "active") === "active";
  const cadence = cadenceValue(source?.scanCadence);
  const nextScanLabel = cadence === "manual" ? "Manual only" : formatDate(source?.nextScanAt, true);
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-lg bg-amber-400/10 text-amber-400">{icon}</span>
          <div>
            <p className="text-[13px] font-semibold text-white">{name}</p>
            <p className="text-[10px] uppercase tracking-wide text-slate-500">PORTAL &middot; {sourceKey}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase",
            active ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400" : "border-slate-500/30 bg-slate-500/10 text-slate-400")}>
            <RadioTower className="size-3" /> {active ? "ACTIVE" : "INACTIVE"}
          </span>
          {statusUpdating && <Loader2 aria-hidden="true" className="size-4 animate-spin text-slate-400" />}
          <Switch checked={active} disabled={statusUpdating || !source?.sourceKey} aria-busy={statusUpdating}
            onCheckedChange={() => onToggleActive(!active)}
            label={`${active ? "Disable" : "Enable"} ${name} ingestion`} />
        </div>
      </div>
      <p className="mt-2 text-[12px] text-slate-400">{fullName}</p>

      <div className="mt-4 grid grid-cols-2 gap-2 text-center">
        <div className="rounded-lg bg-white/[0.02] py-2">
          <p className="text-[9px] uppercase tracking-wide text-slate-500">Last Scan</p>
          <p className="mt-1 text-[11px] text-slate-300">{formatDate(source?.lastScanAt, true)}</p>
        </div>
        <div className="rounded-lg bg-white/[0.02] py-2">
          <p className="text-[9px] uppercase tracking-wide text-slate-500">Next Scan</p>
          <p className="mt-1 text-[11px] text-slate-300">{nextScanLabel}</p>
        </div>
        <div className="rounded-lg bg-white/[0.02] py-2">
          <p className="text-[9px] uppercase tracking-wide text-slate-500">Status</p>
          <p className={cn("mt-1 text-[11px]", scanStatusClass(source?.lastScanStatus))}>{humanize(source?.lastScanStatus)}</p>
        </div>
        <div className="rounded-lg bg-white/[0.02] py-2">
          <p className="text-[9px] uppercase tracking-wide text-slate-500">Found</p>
          <p className="mt-1 text-[11px] text-slate-300">{source?.opportunitiesFound ?? 0} opps</p>
        </div>
      </div>

      <div className="mt-4">
        <label htmlFor={`scan-cadence-${sourceKey}`} className="mb-1.5 block text-[9px] font-semibold uppercase tracking-wide text-slate-500">
          Scan frequency
        </label>
        <div className="relative">
          <select id={`scan-cadence-${sourceKey}`} value={cadence} disabled={cadenceUpdating || !source?.sourceKey}
            onChange={(e) => onCadenceChange(e.target.value as SalesScanCadence)}
            className="w-full cursor-pointer appearance-none rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5 pr-9 text-[12px] text-slate-200 outline-none hover:border-white/20 focus-visible:border-indigo-400/50 focus-visible:ring-2 focus-visible:ring-indigo-400/40 disabled:cursor-not-allowed disabled:opacity-50">
            {SCAN_CADENCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-[#0a0f1a] text-slate-200">{o.label}</option>
            ))}
          </select>
          {cadenceUpdating
            ? <Loader2 className="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 animate-spin text-slate-400" />
            : <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />}
        </div>
        <p className="mt-1.5 text-[10px] text-slate-500">
          {cadence === "manual" ? "Auto-scan off. Use Run Scan when needed." : "Runs on this schedule while the source is enabled."}
        </p>
      </div>

      <button onClick={onScan} disabled={scanning}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-500 py-2.5 text-[13px] font-semibold text-white hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
        <RefreshCw className={cn("size-4", scanning && "animate-spin")} /> {scanning ? "Scanning\u2026" : "Run Scan"}
      </button>
      {error && <p className="mt-2 text-[11px] text-red-400">Couldn&apos;t run the scan. Please try again.</p>}
    </div>
  );
}

function FilterCard({ icon, title, description, enabled, onToggle, helper, children }: {
  icon: React.ReactNode; title: string; description: string; enabled: boolean; onToggle: () => void; helper: string; children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-white/[0.05] text-slate-400">{icon}</span>
          <div>
            <p className="text-[13px] font-semibold text-white">{title}</p>
            <p className="mt-0.5 text-[12px] leading-relaxed text-slate-500">{description}</p>
          </div>
        </div>
        <Switch checked={enabled} onCheckedChange={onToggle} label={title} />
      </div>
      {children}
      <p className="mt-3 text-[11px] text-slate-500">{helper}</p>
    </div>
  );
}
