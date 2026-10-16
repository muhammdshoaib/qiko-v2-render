"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Globe, Layers, Loader2, Plus, RadioTower, RefreshCw, Search, Sparkles, Trash2 } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  createSalesSource, deleteSalesSource, getSalesIngestFilter, getSalesSourcesCatalog, listAgents,
  listSalesOpportunities, listSalesSources, scanSalesSource, updateSalesIngestFilter, updateSalesSource,
  type SalesIntelSource, type SalesScanCadence, type SalesSourceCatalogItem,
} from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { useConfirmActionDialog } from "@/components/confirm-action-dialog";
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
  if (s.includes("success") || s.includes("complete") || s.includes("ok")) return "text-emerald-700";
  if (!s) return "text-slate-500";
  return "text-slate-600";
}

export default function SalesIntelligenceIngestionPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { openConfirmationDialog, closeConfirmationDialog, setPending, ConfirmActionDialog } = useConfirmActionDialog();
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

  // Load the persisted ingest filter and seed the controls once (so the saved keyword + allowlist
  // bypasses survive a reload, matching deployed Staging). Local edits after seeding are the user's.
  const ingestFilterQ = useQuery({ queryKey: ["sales-ingest-filter", agentId], queryFn: () => getSalesIngestFilter(agentId), retry: false });
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || !ingestFilterQ.data) return;
    seeded.current = true;
    setQuery(ingestFilterQ.data.queryKeyword ?? "security");
    setUseQuery(ingestFilterQ.data.queryEnabled);
    setAllCountries(ingestFilterQ.data.allCountries);
    setAllCategories(ingestFilterQ.data.allCategories);
  }, [ingestFilterQ.data]);
  const saveFilter = useMutation({
    mutationFn: () => updateSalesIngestFilter(agentId, {
      query_enabled: useQuery_, query_keyword: query, all_countries: allCountries, all_categories: allCategories,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales-ingest-filter", agentId] }),
  });

  // Scan payload: the keyword (when enabled) plus the two allowlist-bypass toggles, so the
  // "All countries" / "All categories" switches actually reach the portal scan instead of being
  // inert local state.
  const scanBody = () => ({
    query: useQuery_ ? query : undefined,
    all_countries: allCountries,
    all_categories: allCategories,
  });
  const invalidateSources = () => {
    qc.invalidateQueries({ queryKey: ["sales-sources", agentId] });
    qc.invalidateQueries({ queryKey: ["sales-sources-catalog", agentId] });
    qc.invalidateQueries({ queryKey: ["sales-opportunities", agentId] });
  };

  // Scan a source by key: built-in ted/ungm and custom (generic) sources all go through the
  // generic scan route (the server keeps /scan/ted + /scan/ungm precedence for the built-ins).
  const scanMut = useMutation({
    mutationFn: (sourceKey: string) => scanSalesSource(agentId, sourceKey, scanBody()),
    onSuccess: invalidateSources,
  });
  const scanningKey = scanMut.isPending ? scanMut.variables : null;

  // Per-source scan-cadence change. Tracks the in-flight source key so only that card shows a
  // loading state while the mutation settles.
  const cadenceMut = useMutation({
    mutationFn: ({ sourceKey, cadence }: { sourceKey: string; cadence: SalesScanCadence }) =>
      updateSalesSource(agentId, sourceKey, { scan_cadence: cadence }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales-sources", agentId] }),
  });
  const updatingCadenceKey = cadenceMut.isPending ? cadenceMut.variables?.sourceKey : null;

  // Per-source enable/disable. Sends the documented "active"/"inactive" status; the backend
  // rejects scans of an inactive source, so this is the on/off switch for scheduled ingestion.
  const statusMut = useMutation({
    mutationFn: ({ sourceKey, active }: { sourceKey: string; active: boolean }) =>
      updateSalesSource(agentId, sourceKey, { status: active ? "active" : "inactive" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales-sources", agentId] }),
  });
  const updatingStatusKey = statusMut.isPending ? statusMut.variables?.sourceKey : null;

  // Remove an attached source (built-in or custom); opportunities keep their source_key server-side.
  const deleteMut = useMutation({
    mutationFn: (sourceKey: string) => deleteSalesSource(agentId, sourceKey),
    onSuccess: invalidateSources,
  });
  const deletingKey = deleteMut.isPending ? deleteMut.variables : null;

  // Add-source: catalog list + attach (catalog portal or custom URL).
  const catalogQ = useQuery({ queryKey: ["sales-sources-catalog", agentId], queryFn: () => getSalesSourcesCatalog(agentId), retry: false });
  const createMut = useMutation({
    mutationFn: (body: { source_key: string; name?: string; config?: { url?: string } }) => createSalesSource(agentId, body),
    onSuccess: invalidateSources,
  });

  const activeSources = sources.filter((s) => s.status === "active").length;
  const newFromLastScan = useMemo(() => opps.filter((o) => o.stage === "ingested").length, [opps]);

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="ingestion">
      {ConfirmActionDialog}
      <div className="space-y-6">
        <OutcomesStrip title="INGESTION" tiles={[
          { value: String(activeSources), label: "Active Sources", caption: "ingestion portals", trend: "up" },
          { value: String(opps.length), label: "Opportunities Ingested", caption: "all time", trend: "up" },
          { value: String(newFromLastScan), label: "New from Last Scan", caption: "ready to qualify", trend: "up" },
        ]} />

        <div className="rounded-2xl border border-border bg-muted/40 p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-[15px] font-semibold text-foreground">Portal ingestion</h2>
              <p className="mt-1 max-w-2xl text-[13px] text-slate-400">
                Pull tenders from active portals, apply IDG country and category filters, then stage matches as{" "}
                <span className="font-semibold text-slate-700">Ingested</span> for qualification.
              </p>
            </div>
            <div className="shrink-0 rounded-xl border border-border bg-muted/50 px-4 py-2.5 text-center">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Active Sources</p>
              <p className="mt-0.5 text-[15px] font-bold text-foreground">{activeSources} / {sources.length}</p>
            </div>
          </div>

          {sources.length === 0 && !sourcesQ.isLoading && (
            <p className="mt-5 text-[13px] text-slate-500">No sources yet. Add a portal from the catalog or a custom source below.</p>
          )}
          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {sources.map((s) => (
              <SourceCard key={s.sourceKey} icon={sourceIcon(s.sourceKey)} name={s.name} sourceKey={s.sourceKey.toUpperCase()}
                fullName={(s.config?.url as string) || s.type} source={s}
                scannable={s.config?.scannable !== false}
                onScan={() => scanMut.mutate(s.sourceKey)} scanning={scanningKey === s.sourceKey} error={scanMut.isError && scanMut.variables === s.sourceKey}
                onCadenceChange={(cadence) => cadenceMut.mutate({ sourceKey: s.sourceKey, cadence })} cadenceUpdating={updatingCadenceKey === s.sourceKey}
                onToggleActive={(active) => statusMut.mutate({ sourceKey: s.sourceKey, active })} statusUpdating={updatingStatusKey === s.sourceKey}
                onDelete={(opener) => openConfirmationDialog({
                  title: "Delete source",
                  description: `Delete ${s.name}? It will be removed from this agent. You can add the same source key again later to restore it.`,
                  confirmLabel: "Delete",
                  isDestructive: true,
                  onConfirm: () => {
                    setPending(true);
                    deleteMut.mutate(s.sourceKey, {
                      onSuccess: () => closeConfirmationDialog(),
                      onSettled: () => setPending(false),
                    });
                  },
                }, opener)}
                deleting={deletingKey === s.sourceKey} />
            ))}
          </div>

          <AddSourcePanel
            catalog={catalogQ.data?.catalog ?? []}
            onAddCatalog={(key) => createMut.mutate({ source_key: key })}
            onAddCustom={(sourceKey, name, url) => createMut.mutate({ source_key: sourceKey, name, config: { url } })}
            pending={createMut.isPending}
            error={createMut.isError ? "Couldn't add the source. Check the key/URL and try again." : null} />
        </div>

        <div>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
              <Sparkles className="size-3.5" /> INGEST FILTERS
            </p>
            <button type="button" onClick={() => saveFilter.mutate()} disabled={saveFilter.isPending}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border bg-muted px-3.5 py-1.5 text-[12px] font-semibold text-slate-700 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
              {saveFilter.isPending ? <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> : <Check className="size-3.5" aria-hidden="true" />}
              {saveFilter.isPending ? "Saving\u2026" : saveFilter.isSuccess ? "Saved" : "Save filters"}
            </button>
          </div>
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

function SourceCard({ icon, name, sourceKey, fullName, source, scannable = true, onScan, scanning, error, onCadenceChange, cadenceUpdating, onToggleActive, statusUpdating, onDelete, deleting }: {
  icon: React.ReactNode; name: string; sourceKey: string; fullName: string;
  source?: SalesIntelSource; scannable?: boolean; onScan: () => void; scanning: boolean; error?: boolean;
  onCadenceChange: (cadence: SalesScanCadence) => void; cadenceUpdating: boolean;
  onToggleActive: (active: boolean) => void; statusUpdating: boolean;
  onDelete?: (opener: HTMLElement) => void; deleting?: boolean;
}) {
  const active = (source?.status ?? "active") === "active";
  const cadence = cadenceValue(source?.scanCadence);
  const nextScanLabel = cadence === "manual" ? "Manual only" : formatDate(source?.nextScanAt, true);
  return (
    <div className="rounded-xl border border-slate-200 bg-muted/50 p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-lg bg-amber-400/10 text-amber-700">{icon}</span>
          <div>
            <p className="text-[13px] font-semibold text-foreground">{name}</p>
            <p className="text-[10px] uppercase tracking-wide text-slate-500">PORTAL &middot; {sourceKey}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase",
            active ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700" : "border-slate-500/30 bg-slate-500/10 text-slate-400")}>
            <RadioTower className="size-3" /> {active ? "ACTIVE" : "INACTIVE"}
          </span>
          {statusUpdating && <Loader2 aria-hidden="true" className="size-4 animate-spin text-slate-400" />}
          <Switch checked={active} disabled={statusUpdating || !source?.sourceKey} aria-busy={statusUpdating}
            onCheckedChange={() => onToggleActive(!active)}
            label={`${active ? "Disable" : "Enable"} ${name} ingestion`} />
          {onDelete && (
            <button type="button" onClick={(e) => onDelete?.(e.currentTarget)} disabled={deleting} aria-label={`Remove ${name}`}
              className="flex size-11 items-center justify-center rounded-lg border border-border text-slate-400 hover:border-red-500/40 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50 disabled:opacity-50">
              {deleting ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Trash2 className="size-4" aria-hidden="true" />}
            </button>
          )}
        </div>
      </div>
      <p className="mt-2 text-[12px] text-slate-400">{fullName}</p>

      <div className="mt-4 grid grid-cols-2 gap-2 text-center">
        <div className="rounded-lg bg-muted/50 py-2">
          <p className="text-[9px] uppercase tracking-wide text-slate-500">Last Scan</p>
          <p className="mt-1 text-[11px] text-slate-600">{formatDate(source?.lastScanAt, true)}</p>
        </div>
        <div className="rounded-lg bg-muted/50 py-2">
          <p className="text-[9px] uppercase tracking-wide text-slate-500">Next Scan</p>
          <p className="mt-1 text-[11px] text-slate-600">{nextScanLabel}</p>
        </div>
        <div className="rounded-lg bg-muted/50 py-2">
          <p className="text-[9px] uppercase tracking-wide text-slate-500">Status</p>
          <p className={cn("mt-1 text-[11px]", scanStatusClass(source?.lastScanStatus))}>{humanize(source?.lastScanStatus)}</p>
        </div>
        <div className="rounded-lg bg-muted/50 py-2">
          <p className="text-[9px] uppercase tracking-wide text-slate-500">Found</p>
          <p className="mt-1 text-[11px] text-slate-600">{source?.opportunitiesFound ?? 0} opps</p>
        </div>
      </div>

      <div className="mt-4">
        <label htmlFor={`scan-cadence-${sourceKey}`} className="mb-1.5 block text-[9px] font-semibold uppercase tracking-wide text-slate-500">
          Scan frequency
        </label>
        <div className="relative">
          <select id={`scan-cadence-${sourceKey}`} value={cadence} disabled={cadenceUpdating || !source?.sourceKey}
            onChange={(e) => onCadenceChange(e.target.value as SalesScanCadence)}
            className="w-full cursor-pointer appearance-none rounded-lg border border-border bg-muted px-3 py-2.5 pr-9 text-[12px] text-slate-700 outline-none hover:border-border focus-visible:border-indigo-400/50 focus-visible:ring-2 focus-visible:ring-indigo-400/40 disabled:cursor-not-allowed disabled:opacity-50">
            {SCAN_CADENCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-card text-slate-700">{o.label}</option>
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

      <button onClick={onScan} disabled={scanning || !scannable}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-500 py-2.5 text-[13px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
        <RefreshCw className={cn("size-4", scanning && "animate-spin")} /> {scanning ? "Scanning\u2026" : "Run Scan"}
      </button>
      {!scannable && <p className="mt-2 text-[10px] text-slate-500">This source is not yet scannable.</p>}
      {error && <p className="mt-2 text-[11px] text-red-400">Couldn&apos;t run the scan. Please try again.</p>}
    </div>
  );
}

function sourceIcon(key: string): React.ReactNode {
  if (key === "ted") return <Layers className="size-5" />;
  if (key === "ungm") return <RadioTower className="size-5" />;
  return <Globe className="size-5" />;
}

function AddSourcePanel({ catalog, onAddCatalog, onAddCustom, pending, error }: {
  catalog: SalesSourceCatalogItem[]; onAddCatalog: (key: string) => void;
  onAddCustom: (sourceKey: string, name: string, url: string) => void; pending: boolean; error: string | null;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const available = catalog.filter((c) => !c.alreadyAdded);
  // Slugify the name into a valid source_key (^[a-z][a-z0-9_-]{1,63}$).
  const customKey = name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 63);
  const canAddCustom = name.trim().length > 0 && customKey.length >= 2 && /^[a-z]/.test(customKey) && /^https?:\/\//i.test(url.trim());
  return (
    <div className="mt-6 rounded-2xl border border-border bg-muted/40 p-5">
      <p className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
        <Plus className="size-3.5" aria-hidden="true" /> ADD SOURCE
      </p>
      {available.length > 0 && (
        <div className="mb-4">
          <p className="mb-2 text-[11px] text-slate-400">From catalog</p>
          <div className="flex flex-wrap gap-2">
            {available.map((c) => (
              <button key={c.key} type="button" onClick={() => onAddCatalog(c.key)} disabled={pending}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
                <Plus className="size-3.5" aria-hidden="true" /> {c.name}
              </button>
            ))}
          </div>
        </div>
      )}
      <div>
        <p className="mb-2 text-[11px] text-slate-400">Custom source</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Source name" aria-label="Custom source name" />
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://portal.example/search" aria-label="Custom source URL" />
          <button type="button" disabled={!canAddCustom || pending}
            onClick={() => { onAddCustom(customKey, name.trim(), url.trim()); setName(""); setUrl(""); }}
            className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-lg bg-indigo-500 px-4 text-[12px] font-semibold text-foreground hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:opacity-50">
            {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> : <Plus className="size-3.5" aria-hidden="true" />} Add
          </button>
        </div>
        <p className="mt-1.5 text-[10px] text-slate-500">Custom sources are scanned via the generic connector (public http(s) URL only).</p>
      </div>
      {error && <p className="mt-2 text-[11px] text-red-400">{error}</p>}
    </div>
  );
}

function FilterCard({ icon, title, description, enabled, onToggle, helper, children }: {
  icon: React.ReactNode; title: string; description: string; enabled: boolean; onToggle: () => void; helper: string; children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-muted/50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-slate-50 text-slate-400">{icon}</span>
          <div>
            <p className="text-[13px] font-semibold text-foreground">{title}</p>
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
