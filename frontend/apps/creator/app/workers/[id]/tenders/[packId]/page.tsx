"use client";

import { Fragment, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, ArrowRight, Check, ChevronRight, Download, FileCheck2, FileText,
  Layers, RefreshCw, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, Trash2, Upload,
} from "lucide-react";
import { Badge, Button, Card, CardContent, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { AnswerMarkdown, ChatBubble, TypingIndicator } from "@/components/chat-message";
import {
  askBidContext, type Answer, complianceCheck, type ComplianceItem, deleteDocument, exportUrl, extractFromUrl, getAnswers, getRfpPack,
  ingestFile, listDocuments, listRequirements, scoreOpportunity, submitFeedback, tenderBrief, type TenderBrief,
} from "@/lib/api";
import { formatShortDate } from "@/lib/stringUtils";

const TABS = ["Overview", "Sources", "Tender Brief", "Sections", "Compliance", "Chat", "Export"] as const;
type Tab = (typeof TABS)[number];

// Same 5 words the real idg.qiko.ai cockpit shows above the Sections table.
const STAGES = ["Parsed", "Assigned", "Drafting", "Review", "Final"] as const;

const STATUS_STYLE: Record<string, [string, string]> = {
  answered: ["#34d399", "AI-drafted"],
  escalate_human: ["#fbbf24", "For human review"],
  idg_data: ["#22d3ee", "IDG data / table"],
  idg_manual: ["#94a3b8", "IDG commercial"],
  idg_confirmation: ["#94a3b8", "IDG confirmation"],
};

function statusOf(a: Answer): string {
  if (a.classification === "MANUAL") return "idg_manual";
  if (a.classification === "DATA") return "idg_data";
  if (a.classification === "COMPLIANCE") return "idg_confirmation";
  return a.status === "auto_accept" ? "answered" : "escalate_human";
}

export default function TenderCockpitPage() {
  const { id, packId } = useParams<{ id: string; packId: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab");
  const [tab, setTab] = useState<Tab>(TABS.includes(initialTab as Tab) ? (initialTab as Tab) : "Overview");
  const [view, setView] = useState<"list" | "editor">("list");
  const [section, setSection] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const pack = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });
  const requirements = useQuery({ queryKey: ["rfp-requirements", packId], queryFn: () => listRequirements(packId) });
  // Same generate-once-and-cache-client-side pattern as the real cockpit's boot() -- each KB
  // requirement triggers a live LLM call, so this is not something to refetch on every render.
  const answers = useQuery({
    queryKey: ["rfp-answers", packId], queryFn: () => getAnswers(packId),
    enabled: (requirements.data?.length ?? 0) > 0, staleTime: Infinity,
  });
  const sources = useQuery({ queryKey: ["documents"], queryFn: listDocuments });

  const openTab = (t: Tab) => { setTab(t); setView("list"); };

  return (
    <AppShell title="Tender">
      <div className="space-y-4">
        <button onClick={() => router.push(`/workers/${id}`)}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to worker
        </button>

        <div className="flex items-center gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary to-secondary text-white">
            <Sparkles className="size-4" />
          </span>
          <div className="flex-1 min-w-0">
            <p className="font-bold leading-tight truncate" style={{ fontFamily: "var(--font-display)" }}>
              {pack.data?.title ?? "Tender"}
            </p>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              {pack.data?.client_name} <span className="size-1.5 rounded-full bg-emerald-500 inline-block" /> {pack.data?.stage}
            </p>
          </div>
          <p className="text-xs text-muted-foreground shrink-0">Due {formatShortDate(pack.data?.deadline)}</p>
        </div>

        <div className="flex gap-1 border-b border-border overflow-x-auto">
          {TABS.map((t) => (
            <button key={t} onClick={() => openTab(t)}
              className={cn("shrink-0 flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {t}
            </button>
          ))}
        </div>

        {tab === "Overview" && (
          <OverviewTab packId={packId} answers={answers.data} pack={pack.data} onOpenTab={openTab} />
        )}
        {tab === "Sources" && <SourcesTab docs={sources.data} loading={sources.isLoading} onIngested={() => qc.invalidateQueries({ queryKey: ["documents"] })} />}
        {tab === "Tender Brief" && <BriefTab packId={packId} documentText={pack.data?.document_text ?? ""} />}
        {tab === "Sections" && view === "list" && (
          <SectionsTab answers={answers.data} loading={answers.isFetching}
            onOpenSection={(reqId) => { setSection(reqId); setView("editor"); }}
            onRegenerateAll={async () => qc.setQueryData(["rfp-answers", packId], await getAnswers(packId, true))} />
        )}
        {tab === "Sections" && view === "editor" && section && (
          <SectionEditor packId={packId} answer={answers.data?.find((a) => a.req_id === section)}
            draft={drafts[section] ?? ""} onDraftChange={(v) => setDrafts((d) => ({ ...d, [section]: v }))}
            onBack={() => setView("list")} />
        )}
        {tab === "Compliance" && <ComplianceTab packId={packId} documentText={pack.data?.document_text ?? ""} deadline={formatShortDate(pack.data?.deadline)} />}
        {tab === "Chat" && <ChatTab packId={packId} rfpTitle={pack.data?.title ?? "this tender"} />}
        {tab === "Export" && <ExportTab packId={packId} />}
      </div>
    </AppShell>
  );
}

function outcomeCard(label: string, value: string, sub: string, color?: string) {
  return (
    <Card key={label}>
      <CardContent className="pt-4 pb-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold mt-1" style={{ fontFamily: "var(--font-display)" }}>{value}</p>
        <p className="text-[11px] mt-0.5" style={{ color: color ?? "#64748b" }}>{sub}</p>
      </CardContent>
    </Card>
  );
}

function OverviewTab({ packId, answers, pack, onOpenTab }: {
  packId: string; answers?: Answer[]; pack?: { title: string; client_name: string; deadline: string | null; document_text: string };
  onOpenTab: (t: Tab) => void;
}) {
  const total = answers?.length ?? 0;
  const drafted = answers?.filter((a) => a.answer).length ?? 0;
  const review = answers?.filter((a) => a.classification === "KB" && a.status !== "auto_accept").length ?? 0;
  const srcs = new Set<string>();
  answers?.forEach((a) => a.citations.forEach((c) => srcs.add(c)));

  const score = useMutation({ mutationFn: () => scoreOpportunity(packId) });
  const qc = useQueryClient();
  const [tenderUrl, setTenderUrl] = useState("");
  const importUrl = useMutation({
    mutationFn: () => extractFromUrl(packId, tenderUrl),
    onSuccess: () => { setTenderUrl(""); qc.invalidateQueries({ queryKey: ["rfp-pack", packId] }); qc.invalidateQueries({ queryKey: ["rfp-requirements", packId] }); },
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {outcomeCard("Sections", String(total), "tender appendices")}
        {outcomeCard("AI-drafted", `${drafted}/${total || 0}`, "grounded in KB, cited", "#34d399")}
        {outcomeCard("For human review", String(review), "before use", "#fbbf24")}
        {outcomeCard("KB sources", String(srcs.size), "real documents")}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardContent className="pt-6 space-y-3">
            <p className="font-bold" style={{ fontFamily: "var(--font-display)" }}>{pack?.title ?? "Tender"}</p>
            <p className="text-sm text-muted-foreground">
              {pack?.client_name} {pack?.deadline ? `· Submission due ${formatShortDate(pack.deadline)}` : ""}
            </p>
            <p className="text-sm text-slate-300 leading-relaxed">
              {pack?.document_text ? pack.document_text.slice(0, 280) + "…" : "No tender document uploaded yet."}
            </p>
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={() => onOpenTab("Sections")}><Layers className="size-3.5" /> Review answers</Button>
              <Button size="sm" variant="outline" onClick={() => onOpenTab("Tender Brief")}><FileText className="size-3.5" /> Tender brief</Button>
            </div>
            {!pack?.document_text && (
              <form onSubmit={(e) => { e.preventDefault(); if (tenderUrl.trim()) importUrl.mutate(); }}
                className="flex gap-2 pt-2 border-t border-border">
                <input value={tenderUrl} onChange={(e) => setTenderUrl(e.target.value)}
                  placeholder="Or paste the tender's webpage URL to import it…"
                  className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                <Button type="submit" size="sm" variant="outline" disabled={!tenderUrl.trim() || importUrl.isPending}>
                  {importUrl.isPending ? "Importing…" : "Import"}
                </Button>
              </form>
            )}
            {importUrl.isError && <p className="text-xs text-red-400">Couldn&apos;t import that URL -- check it&apos;s a public, reachable page.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">Should we bid this?</p>
              <Button size="sm" variant="outline" disabled={score.isPending || !pack?.document_text} onClick={() => score.mutate()}>
                {score.isPending ? "Scoring…" : "Score opportunity"}
              </Button>
            </div>
            {!score.data && !score.isPending && (
              <p className="text-xs text-muted-foreground">Qualify this opportunity against this worker&apos;s own criteria (set in Settings) before committing to a full draft.</p>
            )}
            {score.data && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold" style={{ fontFamily: "var(--font-display)", color: score.data.qualified ? "#34d399" : "#fbbf24" }}>{score.data.score}</span>
                  <span className="text-xs text-muted-foreground">/100 · {score.data.qualified ? "Worth pursuing" : "Marginal fit"}</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">{score.data.rationale}</p>
                <ul className="text-xs space-y-1 list-none">
                  {score.data.criteria_results.map((cr, i) => (
                    <li key={i} className="flex gap-1.5 items-start">
                      <span className={cr.met ? "text-emerald-400" : "text-amber-400"}>{cr.met ? "✓" : "△"}</span>
                      <span className="text-muted-foreground">{cr.criterion}{cr.note ? ` — ${cr.note}` : ""}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {score.isError && <p className="text-xs text-red-400">Couldn&apos;t score this opportunity -- try again in a moment.</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SourcesTab({ docs, loading, onIngested }: {
  docs?: { doc_id: string; chunks: number }[]; loading: boolean; onIngested: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const ingestMut = useMutation({
    mutationFn: () => ingestFile(file!.name, file!),
    onSuccess: (res) => { setStatus({ kind: "ok", text: `Ingested ${file!.name} · ${res.chunks} passage(s)` }); setFile(null); onIngested(); },
    onError: () => setStatus({ kind: "err", text: "Ingest failed." }),
  });
  const removeMut = useMutation({
    mutationFn: (docId: string) => deleteDocument(docId),
    onSuccess: () => { setStatus(null); onIngested(); },
    onError: () => setStatus({ kind: "err", text: "Couldn't remove that document." }),
  });
  const totalChunks = docs?.reduce((n, d) => n + d.chunks, 0) ?? 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {outcomeCard("Documents ingested", String(docs?.length ?? 0), "past bids + company docs", "#22d3ee")}
        {outcomeCard("Passages indexed", String(totalChunks), "searchable")}
        {outcomeCard("Source families", String(docs?.length ?? 0), "in the knowledge base")}
        {outcomeCard("Embeddings", "local", "private")}
      </div>
      <div>
        <h2 className="font-bold text-lg mb-1" style={{ fontFamily: "var(--font-display)" }}>Sources &amp; Ingestion</h2>
        <p className="text-xs text-muted-foreground mb-3">
          The knowledge base the worker answers from, live from the index. Add documents to ingest them (extract, chunk, embed) and they appear here immediately.
        </p>
      </div>
      <Card>
        <CardContent className="pt-4 pb-4 space-y-2">
          <p className="text-sm font-semibold">Add documents</p>
          <div className="flex items-center gap-3 flex-wrap">
            <label className="inline-flex items-center gap-2 text-sm px-3 py-2 rounded-lg cursor-pointer border border-input bg-muted/40">
              <Upload className="size-4" /> Choose file
              <input type="file" accept=".pdf,.docx,.txt,.md" className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </label>
            <span className="text-xs text-muted-foreground">{file?.name ?? ""}</span>
            <Button size="sm" disabled={!file || ingestMut.isPending} onClick={() => ingestMut.mutate()}>
              {ingestMut.isPending ? "Ingesting…" : "Ingest"}
            </Button>
          </div>
          {status && (
            <p className={cn("text-xs", status.kind === "ok" ? "text-emerald-400" : "text-destructive")}>{status.text}</p>
          )}
        </CardContent>
      </Card>
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {docs?.map((d) => (
          <Card key={d.doc_id}>
            <CardContent className="pt-4 pb-4 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{d.doc_id}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">{d.chunks} passages</p>
              </div>
              <button type="button" aria-label={`Remove ${d.doc_id}`} disabled={removeMut.isPending}
                onClick={() => removeMut.mutate(d.doc_id)}
                className="shrink-0 rounded-md p-1 text-pink-300/60 transition-colors hover:bg-red-500/10 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/50 disabled:opacity-50">
                <Trash2 className="size-4" />
              </button>
            </CardContent>
          </Card>
        ))}
        {docs?.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground">Knowledge base is empty. Add a document above.</p>
        )}
      </div>
    </div>
  );
}

function BriefTab({ packId, documentText }: { packId: string; documentText: string }) {
  const [brief, setBrief] = useState<TenderBrief | null>(null);
  const gen = useMutation({ mutationFn: () => tenderBrief(packId, documentText), onSuccess: setBrief });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-bold text-lg" style={{ fontFamily: "var(--font-display)" }}>Tender Brief</h2>
        <p className="text-xs text-muted-foreground">What this tender is, how to bid, and where you have gaps. Understood from the tender documents.</p>
      </div>
      {!brief && (
        <Button onClick={() => gen.mutate()} disabled={!documentText || gen.isPending}>
          <Sparkles className="size-4" /> {gen.isPending ? "Generating…" : "Generate tender brief"}
        </Button>
      )}
      {!documentText && <p className="text-sm text-muted-foreground">No tender document on file for this pack.</p>}
      {gen.isError && <p className="text-sm text-destructive">Could not generate a brief -- try again.</p>}
      {brief && (
        <div className="space-y-4">
          <Card>
            <CardContent className="pt-4 pb-4 space-y-3">
              <div>
                <p className="text-sm font-semibold mb-1">Summary</p>
                <p className="text-sm leading-relaxed text-slate-200">{brief.summary || "Not yet generated for this tender."}</p>
              </div>
              {brief.scope && (
                <div><p className="text-sm font-semibold mb-1">Scope</p><p className="text-sm text-muted-foreground">{brief.scope}</p></div>
              )}
              {brief.submission_format && (
                <div><p className="text-sm font-semibold mb-1">Submission format</p><p className="text-sm text-muted-foreground">{brief.submission_format}</p></div>
              )}
            </CardContent>
          </Card>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <BulletCard title="Key dates" items={brief.key_dates} color="#22d3ee" />
            <BulletCard title="Success criteria" items={brief.success_criteria} color="#6366F1" />
          </div>
          <BulletCard title="Gaps &amp; risks" items={brief.gaps_and_risks} color="#fbbf24" />
        </div>
      )}
    </div>
  );
}

function BulletCard({ title, items, color }: { title: string; items: string[]; color: string }) {
  return (
    <Card>
      <CardContent className="pt-4 pb-4">
        <p className="text-sm font-semibold mb-2" dangerouslySetInnerHTML={{ __html: title }} />
        <ul className="space-y-1.5 text-sm text-slate-300 list-none">
          {items?.length ? items.map((x, i) => (
            <li key={i} className="flex gap-2"><span style={{ color }}>•</span><span>{x}</span></li>
          )) : <li className="text-muted-foreground">Not specified</li>}
        </ul>
      </CardContent>
    </Card>
  );
}

// A dotted req_id ("B1.1") groups under its parent ("B1") -- same convention the extraction
// prompt uses (rfp/extraction.py) so a section with multiple distinct numbered sub-requirements
// becomes one foldable row with its own independently-reviewable sub-sections, matching the
// reference idg.qiko.ai cockpit, instead of one flat row per sub-item.
function parentIdOf(reqId: string): string {
  const i = reqId.indexOf(".");
  return i === -1 ? reqId : reqId.slice(0, i);
}

// The extraction prompt encodes "Parent Title — Own Title" into a dotted item's title so the
// group header has a real name instead of a bare id.
function splitTitle(title: string): { parentTitle: string | null; ownTitle: string } {
  const sep = title.indexOf(" \u2014 ");
  if (sep === -1) return { parentTitle: null, ownTitle: title };
  return { parentTitle: title.slice(0, sep), ownTitle: title.slice(sep + 3) };
}

type SectionGroup = { parentId: string; parentTitle: string; items: Answer[] };

function groupSections(answers: Answer[]): SectionGroup[] {
  const order: string[] = [];
  const byParent = new Map<string, Answer[]>();
  for (const a of answers) {
    const pid = parentIdOf(a.req_id);
    if (!byParent.has(pid)) { byParent.set(pid, []); order.push(pid); }
    byParent.get(pid)!.push(a);
  }
  return order.map((parentId) => {
    const items = byParent.get(parentId)!;
    const withParentTitle = items.map((it) => splitTitle(it.req_title).parentTitle).find(Boolean);
    return { parentId, parentTitle: withParentTitle || splitTitle(items[0].req_title).ownTitle, items };
  });
}

function SectionsTab({ answers, loading, onOpenSection, onRegenerateAll }: {
  answers?: Answer[]; loading: boolean;
  onOpenSection: (reqId: string) => void;
  onRegenerateAll: () => Promise<unknown>;
}) {
  const [regenerating, setRegenerating] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const a = answers ?? [];
  const groups = groupSections(a);
  const drafted = a.filter((x) => x.answer).length;
  const tot = a.length || 1;
  const avg = (arr: number[]) => (arr.length ? Math.round((arr.reduce((s, v) => s + (v || 0), 0) / arr.length) * 100) : 0);
  const withAnswer = a.filter((x) => x.answer);
  const avgConf = avg(withAnswer.map((x) => x.confidence));
  const avgGround = avg(withAnswer.map((x) => x.grounding));
  const cur = 3; // Parsed -> Assigned -> Drafting are done once drafts exist; Review is where a human is now.

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-bold text-lg mb-1" style={{ fontFamily: "var(--font-display)" }}>Sections (RFP requirements)</h2>
          <p className="text-xs text-muted-foreground">Each section is a requirement from the RFP. Every AI draft is for human review before use.</p>
        </div>
        <Button size="sm" variant="outline" disabled={regenerating}
          onClick={() => { setRegenerating(true); onRegenerateAll().finally(() => setRegenerating(false)); }}>
          <RefreshCw className={cn("size-3.5", regenerating && "animate-spin")} /> {regenerating ? "Regenerating…" : "Regenerate all"}
        </Button>
      </div>
      {(loading || regenerating) && <p className="text-sm text-muted-foreground">Generating drafts from your knowledge base… this can take a moment.</p>}
      <Card>
        <CardContent className="pt-4 pb-4 flex items-center gap-6">
          <div className="flex-[2]">
            <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
              <span>AI-drafted (for your review)</span><span>{drafted} / {a.length}</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div className="h-full rounded-full bg-gradient-to-r from-primary to-cyan-400" style={{ width: `${Math.round((drafted / tot) * 100)}%` }} />
            </div>
          </div>
          <div className="flex-1"><p className="text-[11px] text-muted-foreground">Avg confidence</p><p className="text-xl font-bold" style={{ fontFamily: "var(--font-display)" }}>{avgConf}%</p></div>
          <div className="flex-1"><p className="text-[11px] text-muted-foreground">Avg grounding</p><p className="text-xl font-bold" style={{ fontFamily: "var(--font-display)" }}>{avgGround}%</p></div>
        </CardContent>
      </Card>
      <div>
        <div className="flex items-center gap-1 mb-1">
          {STAGES.map((s, i) => (
            <div key={s} className="flex-1 h-1.5 rounded-full" style={{ background: i < cur ? "#34d399" : i === cur ? "#6366F1" : "#1f2937" }} />
          ))}
        </div>
        <div className="flex justify-between text-[11px]">
          {STAGES.map((s, i) => (
            <span key={s} className="inline-flex items-center gap-1" style={{ color: i < cur ? "#34d399" : i === cur ? "#a5b4fc" : "#64748b" }}>
              {i < cur && <Check className="size-3" />}{s}
            </span>
          ))}
        </div>
      </div>
      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground bg-white/[0.03]">
            <tr><th className="text-left p-3">#</th><th className="text-left p-3">Section</th><th className="text-left p-3">Gaps</th><th className="text-left p-3">Status</th><th className="p-3" /></tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const hasSubSections = g.items.length > 1;
              const isOpen = expanded[g.parentId] ?? false;
              const anyGap = g.items.some((x) => !!x.note);
              const anyEscalated = g.items.some((x) => statusOf(x) === "escalate_human");
              return (
                <Fragment key={g.parentId}>
                  <tr className={cn("border-t border-border transition-colors",
                    !hasSubSections && "hover:bg-white/[0.02] cursor-pointer")}
                    onClick={hasSubSections ? undefined : () => onOpenSection(g.items[0].req_id)}>
                    <td className="p-3 text-muted-foreground align-top">{g.parentId}</td>
                    <td className="p-3">
                      <span className="font-medium inline-flex items-center gap-1.5">
                        {hasSubSections && (
                          <ChevronRight className={cn("size-3.5 text-muted-foreground transition-transform", isOpen && "rotate-90")} />
                        )}
                        {g.parentTitle}
                        {hasSubSections && <span className="text-[11px] text-muted-foreground">({g.items.length} sub-sections)</span>}
                      </span>
                      {!hasSubSections && g.items[0].note && (
                        <div className="text-[11px] text-muted-foreground mt-0.5">{g.items[0].note}</div>
                      )}
                    </td>
                    <td className="p-3 text-xs">
                      {anyGap
                        ? <span className="inline-flex items-center gap-1 text-amber-400"><ShieldCheck className="size-3" /> KB gap</span>
                        : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="p-3 text-xs">
                      {hasSubSections
                        ? (anyEscalated
                            ? <span className="inline-flex items-center gap-1" style={{ color: STATUS_STYLE.escalate_human[0] }}>{STATUS_STYLE.escalate_human[1]}</span>
                            : <span className="inline-flex items-center gap-1" style={{ color: STATUS_STYLE.answered[0] }}><Check className="size-3.5" />{STATUS_STYLE.answered[1]}</span>)
                        : (() => { const [c, l] = STATUS_STYLE[statusOf(g.items[0])] ?? ["#94a3b8", statusOf(g.items[0])];
                            return <span className="inline-flex items-center gap-1" style={{ color: c }}>{statusOf(g.items[0]) === "answered" && <Check className="size-3.5" />}{l}</span>; })()}
                    </td>
                    <td className="p-3 text-right">
                      {hasSubSections ? (
                        <button className="text-[#a5b4fc] text-sm" onClick={(e) => { e.stopPropagation(); setExpanded((s) => ({ ...s, [g.parentId]: !isOpen })); }}>
                          {isOpen ? "Collapse" : "Expand"}
                        </button>
                      ) : (
                        <span className="text-[#a5b4fc] text-sm inline-flex items-center gap-1">Open <ChevronRight className="size-3.5" /></span>
                      )}
                    </td>
                  </tr>
                  {hasSubSections && isOpen && g.items.map((x) => (
                    <tr key={x.req_id} className="border-t border-border/60 bg-white/[0.015] hover:bg-white/[0.03] cursor-pointer transition-colors"
                      onClick={() => onOpenSection(x.req_id)}>
                      <td className="p-3 pl-8 align-top">
                        <span className="rounded-md bg-primary/15 px-1.5 py-0.5 text-[11px] font-medium text-primary">{x.req_id}</span>
                      </td>
                      <td className="p-3" colSpan={3}>
                        <div className="font-medium">{splitTitle(x.req_title).ownTitle}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                          {x.answer && (
                            <>
                              <span className="inline-flex items-center gap-1">conf
                                <span className="h-1 w-10 rounded-full bg-white/10 overflow-hidden inline-block">
                                  <span className="h-full block bg-emerald-400" style={{ width: `${Math.round(x.confidence * 100)}%` }} />
                                </span> {Math.round(x.confidence * 100)}%
                              </span>
                              <span className="inline-flex items-center gap-1">grounding
                                <span className="h-1 w-10 rounded-full bg-white/10 overflow-hidden inline-block">
                                  <span className="h-full block bg-cyan-400" style={{ width: `${Math.round(x.grounding * 100)}%` }} />
                                </span> {Math.round(x.grounding * 100)}%
                              </span>
                            </>
                          )}
                          {x.note && <span className="inline-flex items-center gap-1 text-amber-400"><ShieldCheck className="size-3" /> gaps</span>}
                          {(() => { const [c, l] = STATUS_STYLE[statusOf(x)] ?? ["#94a3b8", statusOf(x)];
                            return <span style={{ color: c }}>{l}</span>; })()}
                        </div>
                      </td>
                      <td className="p-3 text-right">
                        <span className="text-[#a5b4fc] text-sm inline-flex items-center gap-1">Open <ChevronRight className="size-3.5" /></span>
                      </td>
                    </tr>
                  ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function SectionEditor({ packId, answer, draft, onDraftChange, onBack }: {
  packId: string; answer?: Answer; draft: string; onDraftChange: (v: string) => void; onBack: () => void;
}) {
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const fb = useMutation({
    mutationFn: (vars: { decision: "Approve" | "Edit" | "Reject" }) =>
      submitFeedback(packId, answer!.req_id, vars.decision, draft || answer?.answer || ""),
    onSuccess: (_r, vars) => setSavedMsg(`${vars.decision.toLowerCase()} saved`),
  });

  if (!answer) return <p className="text-sm text-muted-foreground">Section not found.</p>;
  const wc = draft.trim() ? draft.trim().split(/\s+/).length : 0;
  const status = statusOf(answer);
  const [statusColor, statusLabel] = STATUS_STYLE[status] ?? ["#94a3b8", status];
  const hasAI = !!answer.answer;
  const reqLines = (answer.requirement || "").split("\n").map((s) => s.trim()).filter(Boolean);

  const gapLines = (answer.note || "").split(/\n|(?<=\.)\s+(?=[A-Z])/).map((s) => s.trim()).filter(Boolean);
  const { parentTitle, ownTitle } = splitTitle(answer.req_title);

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Back to sections
      </button>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-bold text-lg" style={{ fontFamily: "var(--font-display)" }}>
            <span className="mr-2 rounded-md bg-primary/15 px-1.5 py-0.5 text-xs font-medium text-primary align-middle">{answer.req_id}</span>
            {ownTitle}
          </h2>
          {parentTitle && <p className="text-xs text-muted-foreground mt-0.5">{parentTitle} · validate this sub-section on its own.</p>}
        </div>
        <div className="flex items-center gap-2">
          {hasAI && (
            <>
              <span className="rounded-full px-2 py-0.5 text-xs bg-emerald-500/10 text-emerald-400">conf {Math.round(answer.confidence * 100)}%</span>
              <span className="rounded-full px-2 py-0.5 text-xs bg-cyan-500/10 text-cyan-400">grounding {Math.round(answer.grounding * 100)}%</span>
            </>
          )}
          <span className="px-2 py-0.5 rounded-full text-xs bg-white/[0.06]" style={{ color: statusColor }}>{statusLabel}</span>
        </div>
      </div>
      {gapLines.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.06] p-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-amber-400">
            <ShieldCheck className="size-3.5" /> Gaps for human input
          </p>
          <ul className="space-y-0.5">
            {gapLines.map((line, i) => (
              <li key={i} className="flex gap-2 text-xs text-amber-200/90">
                <span className="text-amber-400">•</span><span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {reqLines.length > 0 && (
        <Card className="border-primary/30 bg-primary/[0.06]">
          <CardContent className="pt-4 pb-4">
            <p className="font-semibold text-sm mb-2 text-indigo-300">Requirement, what the RFP asks for this section</p>
            <div className="space-y-1 max-h-[26vh] overflow-y-auto">
              {reqLines.map((line, i) => (
                <div key={i} className="flex gap-2 items-start text-sm py-0.5">
                  <span className="text-primary">•</span><span className="text-slate-200">{line}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
      {!hasAI ? (
        <Card><CardContent className="pt-4 pb-4 text-sm text-muted-foreground">No AI draft for this section. {answer.note}</CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <CardContent className="pt-4 pb-4">
              <div className="flex items-center justify-between mb-2">
                <p className="font-semibold text-sm">AI suggestion</p>
                <p className="text-[11px] text-muted-foreground">{answer.citations.length} KB source(s)</p>
              </div>
              <div className="max-h-[50vh] overflow-y-auto text-sm leading-relaxed text-slate-200">
                <AnswerMarkdown text={answer.answer} />
              </div>
              <div className="mt-3 border-t border-border pt-2">
                <p className="text-[11px] text-muted-foreground mb-1">Sources</p>
                <div className="flex flex-wrap gap-1">
                  {answer.citations.length
                    ? answer.citations.slice(0, 6).map((s, i) => (
                        <span key={i} className="text-[10px] rounded px-1.5 py-0.5 bg-white/[0.06]">{s.split("/").pop()}</span>
                      ))
                    : <span className="text-xs text-muted-foreground">none</span>}
                </div>
              </div>
              <Button size="sm" className="mt-3" onClick={() => onDraftChange(answer.answer)}>
                Copy to editor <ArrowRight className="size-3.5" />
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 pb-4 flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <p className="font-semibold text-sm">Your response</p>
                <p className="text-[11px] text-muted-foreground">{wc} words</p>
              </div>
              <textarea value={draft} onChange={(e) => onDraftChange(e.target.value)}
                placeholder="Copy the AI suggestion or write your response…"
                className="flex-1 min-h-[44vh] rounded-lg border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
              <div className="mt-3 flex gap-2 flex-wrap items-center">
                <Button size="sm" disabled={fb.isPending} onClick={() => fb.mutate({ decision: "Edit" })}><Check className="size-3.5" /> {fb.isPending ? "Saving…" : "Save draft"}</Button>
                <Button size="sm" variant="ghost" className="text-emerald-400" disabled={fb.isPending} onClick={() => fb.mutate({ decision: "Approve" })}><ThumbsUp className="size-3.5" /> Approve</Button>
                <Button size="sm" variant="ghost" className="text-red-400" disabled={fb.isPending} onClick={() => fb.mutate({ decision: "Reject" })}><ThumbsDown className="size-3.5" /> Reject</Button>
                {savedMsg && <span className="text-xs text-emerald-400 inline-flex items-center gap-1"><Check className="size-3.5" /> {savedMsg}</span>}
                {fb.isError && <span className="text-xs text-red-400">Couldn&apos;t save — try again.</span>}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

const COMPLIANCE_COLORS: Record<string, string> = {
  Legal: "#f87171", Commercial: "#fbbf24", HSSE: "#34d399", Format: "#22d3ee", Experience: "#a5b4fc", Eligibility: "#f472b6",
};

function ComplianceTab({ packId, documentText, deadline }: { packId: string; documentText: string; deadline: string }) {
  const [items, setItems] = useState<ComplianceItem[] | null>(null);
  const gen = useMutation({ mutationFn: () => complianceCheck(packId, documentText), onSuccess: setItems });
  const ai = items?.filter((i) => i.owner === "AI").length ?? 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {outcomeCard("Mandatory items", String(items?.length ?? 0), "pass/fail", "#fbbf24")}
        {outcomeCard("AI can address", String(ai), "from KB", "#34d399")}
        {outcomeCard("Needs input", String((items?.length ?? 0) - ai), "forms/signatures/pricing", "#22d3ee")}
        {outcomeCard("Deadline", deadline, "")}
      </div>
      <div>
        <h2 className="font-bold text-lg mb-1" style={{ fontFamily: "var(--font-display)" }}>Compliance Checker</h2>
        <p className="text-xs text-muted-foreground">Mandatory requirements and disqualifiers extracted from the tender, tagged by who must action each so nothing that could disqualify the bid is missed.</p>
      </div>
      {!items && (
        <Button onClick={() => gen.mutate()} disabled={!documentText || gen.isPending}>
          <ShieldCheck className="size-4" /> {gen.isPending ? "Checking…" : "Run compliance check"}
        </Button>
      )}
      {!documentText && <p className="text-sm text-muted-foreground">No tender document on file for this pack.</p>}
      {gen.isError && <p className="text-sm text-destructive">Could not run the compliance check -- try again.</p>}
      {items && (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground bg-white/[0.03]">
              <tr><th className="text-left p-3">Requirement</th><th className="text-left p-3">Category</th><th className="text-left p-3">Owner</th></tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i} className="border-t border-border hover:bg-white/[0.02]">
                  <td className="p-3">
                    <p className="font-medium">{it.requirement}</p>
                    {it.note && <p className="text-[11px] text-muted-foreground mt-0.5">{it.note}</p>}
                  </td>
                  <td className="p-3 text-xs">
                    <span className="px-2 py-0.5 rounded-full bg-white/[0.06]" style={{ color: COMPLIANCE_COLORS[it.category] ?? "#94a3b8" }}>{it.category}</span>
                  </td>
                  <td className="p-3 text-xs">
                    {it.owner === "AI" ? <span className="text-emerald-400">AI draft</span> : <span className="text-cyan-400">Human input</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function ChatTab({ packId, rfpTitle }: { packId: string; rfpTitle: string }) {
  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<{ role: "bot" | "user"; text: string }[]>([
    { role: "bot", text: `Hi, I've reviewed ${rfpTitle}. Every AI draft is grounded in your knowledge base with cited sources and is for your review before use. Ask me anything about the scope, format, deadlines or risks.` },
  ]);
  const ask = useMutation({
    mutationFn: () => askBidContext(packId, question),
    onSuccess: (res) => setThread((t) => [...t, { role: "bot", text: res.answer }]),
    onError: () => setThread((t) => [...t, { role: "bot", text: "Sorry — I couldn't answer that just now. Please try again in a moment." }]),
  });

  const send = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || ask.isPending) return;
    setThread((t) => [...t, { role: "user", text: question }]);
    ask.mutate();
    setQuestion("");
  };

  return (
    <div className="flex flex-col h-[70vh]">
      <div>
        <h2 className="font-bold text-lg mb-1" style={{ fontFamily: "var(--font-display)" }}>Assistant</h2>
        <p className="text-xs text-muted-foreground mb-3">Ask anything about this tender: scope, format, deadlines, risks.</p>
      </div>
      <Card className="flex-1 overflow-y-auto p-4 space-y-3 mb-3">
        {thread.map((m, i) => (
          <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <ChatBubble role={m.role === "bot" ? "assistant" : "user"} text={m.text} variant="gradient" />
          </div>
        ))}
        {ask.isPending && <div className="flex justify-start"><TypingIndicator variant="gradient" /></div>}
      </Card>
      <form onSubmit={send} className="flex gap-2">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about the tender…"
          className="flex-1 rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <Button type="submit" disabled={ask.isPending || !question.trim()}>Send</Button>
      </form>
    </div>
  );
}

function ExportTab({ packId }: { packId: string }) {
  const options = [
    { kind: "docx-clean" as const, icon: FileCheck2, iconBg: "linear-gradient(135deg,#059669,#22d3ee)", kindLabel: "For the client",
      title: "Submission document", fmt: ".docx", tag: "Recommended", primary: true,
      desc: "Clean and client-ready, organised by section. No annotations, requirement echoes, sources or gap notes." },
    { kind: "docx-review" as const, icon: FileText, iconBg: "linear-gradient(90deg,#6366F1,#22D3EE)", kindLabel: "Internal review",
      title: "Review draft", fmt: ".docx", tag: null, primary: false,
      desc: "Annotated for review: the requirement, confidence and grounding, KB sources and gaps, shown per section." },
    { kind: "xlsx" as const, icon: Layers, iconBg: "rgba(255,255,255,.08)", kindLabel: "Internal review",
      title: "Review sheet", fmt: ".xlsx", tag: null, primary: false,
      desc: "Every section with its answer, confidence, grounding, status and a feedback column for sign-off." },
  ];
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-bold text-lg mb-1" style={{ fontFamily: "var(--font-display)" }}>Export</h2>
        <p className="text-xs text-muted-foreground">Use the clean submission for the client. Keep the annotated review draft and the Excel sheet for internal sign-off.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {options.map((o) => (
          <Card key={o.kind} className="flex flex-col h-full">
            <CardContent className="pt-5 pb-5 flex flex-col h-full">
              <div className="flex items-start justify-between mb-3">
                <span className="grid size-11 place-items-center rounded-xl text-white" style={{ background: o.iconBg }}>
                  <o.icon className="size-5" />
                </span>
                {o.tag && <Badge variant="success">{o.tag}</Badge>}
              </div>
              <div className="flex items-center gap-2">
                <span className="font-semibold">{o.title}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-muted-foreground">{o.fmt}</span>
              </div>
              <p className="text-[11px] uppercase tracking-wide mt-0.5 text-slate-500">{o.kindLabel}</p>
              <p className="text-xs text-muted-foreground mt-2 mb-4 leading-relaxed flex-1">{o.desc}</p>
              <a href={exportUrl(packId, o.kind)} target="_blank" rel="noreferrer">
                <Button className="w-full justify-center" variant={o.primary ? "default" : "outline"}>
                  <Download className="size-3.5" /> Download
                </Button>
              </a>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
