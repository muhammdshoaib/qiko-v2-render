"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, BookOpen, Download, FileCheck2, FileText, Layers, MessageSquare, ShieldCheck, Sparkles,
} from "lucide-react";
import { Badge, Button, Card, CardContent, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  askBidContext, complianceCheck, exportUrl, getRfpPack, listDocuments, listRequirements,
  tenderBrief, type ComplianceItem, type PackRequirement, type TenderBrief,
} from "@/lib/api";

const TABS = ["Overview", "Sources", "Tender Brief", "Sections", "Compliance", "Chat", "Export"] as const;
type Tab = (typeof TABS)[number];

export default function TenderCockpitPage() {
  const { id, packId } = useParams<{ id: string; packId: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("Overview");
  const pack = useQuery({ queryKey: ["rfp-pack", packId], queryFn: () => getRfpPack(packId) });
  const requirements = useQuery({ queryKey: ["rfp-requirements", packId], queryFn: () => listRequirements(packId) });
  const sources = useQuery({ queryKey: ["documents"], queryFn: listDocuments });

  const sectionCount = requirements.data?.length ?? 0;
  const kbCount = requirements.data?.filter((r) => r.classification === "KB").length ?? 0;
  const humanCount = requirements.data?.filter((r) => r.classification !== "KB").length ?? 0;

  return (
    <AppShell title="Tender">
      <div className="space-y-6">
        <button onClick={() => router.push(`/workers/${id}`)}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to worker
        </button>

        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold" style={{ fontFamily: "var(--font-display)" }}>
              {pack.data?.title ?? "Tender"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {pack.data?.client_name} {pack.data?.deadline ? `· Due ${pack.data.deadline}` : ""}
            </p>
          </div>
          {pack.data && <Badge variant="muted">{pack.data.stage}</Badge>}
        </div>

        <div className="flex gap-1 border-b border-border overflow-x-auto">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={cn("shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {t}
            </button>
          ))}
        </div>

        {tab === "Overview" && (
          <OverviewTab sectionCount={sectionCount} kbCount={kbCount} humanCount={humanCount}
            kbSources={sources.data?.length ?? 0} pack={pack.data} onOpenTab={setTab} />
        )}
        {tab === "Sources" && <SourcesTab docs={sources.data} loading={sources.isLoading} />}
        {tab === "Tender Brief" && <BriefTab packId={packId} documentText={pack.data?.document_text ?? ""} />}
        {tab === "Sections" && <SectionsTab requirements={requirements.data} loading={requirements.isLoading} />}
        {tab === "Compliance" && <ComplianceTab packId={packId} documentText={pack.data?.document_text ?? ""} />}
        {tab === "Chat" && <ChatTab packId={packId} />}
        {tab === "Export" && <ExportTab packId={packId} />}
      </div>
    </AppShell>
  );
}

function OverviewTab({ sectionCount, kbCount, humanCount, kbSources, pack, onOpenTab }: {
  sectionCount: number; kbCount: number; humanCount: number; kbSources: number;
  pack?: { title: string; client_name: string; deadline: string | null; document_text: string };
  onOpenTab: (t: Tab) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Sections", value: sectionCount, sub: "tender appendices" },
          { label: "AI-drafted", value: `${kbCount}/${sectionCount}`, sub: "grounded in KB, cited" },
          { label: "For human review", value: humanCount, sub: "before use" },
          { label: "KB sources", value: kbSources, sub: "real documents" },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="pt-5">
              <p className="text-xs font-medium text-muted-foreground">{s.label}</p>
              <p className="mt-1 text-2xl font-semibold">{s.value}</p>
              <p className="text-xs text-muted-foreground">{s.sub}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardContent className="pt-6 space-y-3">
            <p className="text-sm font-semibold">{pack?.title ?? "Tender"}</p>
            <p className="text-xs text-muted-foreground">
              {pack?.client_name} {pack?.deadline ? `· Submission due ${pack.deadline}` : ""}
            </p>
            <p className="text-sm text-muted-foreground line-clamp-4">
              {pack?.document_text ? pack.document_text.slice(0, 320) + "…" : "No tender document uploaded yet."}
            </p>
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={() => onOpenTab("Sections")}>Review sections</Button>
              <Button size="sm" variant="outline" onClick={() => onOpenTab("Tender Brief")}>Tender brief</Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 space-y-2">
            <p className="text-sm font-semibold">How it works</p>
            <p className="text-xs text-muted-foreground">Answers are drafted only from your knowledge base, with cited sources.</p>
            <p className="text-xs text-muted-foreground">A second model checks each draft against the evidence as an internal quality gate.</p>
            <p className="text-xs text-muted-foreground">Drafts that do not clear the internal bar are sent for human review, never auto-accepted.</p>
            <p className="text-xs text-muted-foreground">Your approvals and edits are written back to strengthen the next bid.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SourcesTab({ docs, loading }: { docs?: { doc_id: string; chunks: number }[]; loading: boolean }) {
  return (
    <Card>
      <CardContent className="pt-6 space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold mb-2">
          <BookOpen className="size-4" /> Knowledge base sources
        </div>
        {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {docs?.map((d) => (
          <div key={d.doc_id} className="flex items-center justify-between rounded-lg border border-border/60 p-3 text-sm">
            <span className="truncate">{d.doc_id}</span>
            <Badge variant="muted">{d.chunks} chunks</Badge>
          </div>
        ))}
        {docs?.length === 0 && <p className="text-sm text-muted-foreground">No documents ingested yet.</p>}
      </CardContent>
    </Card>
  );
}

function SectionsTab({ requirements, loading }: { requirements?: PackRequirement[]; loading: boolean }) {
  return (
    <div className="space-y-2">
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {requirements?.map((r) => (
        <Card key={r.id}>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">{r.req_id} · {r.title}</p>
                <p className="mt-1 text-sm text-muted-foreground whitespace-pre-wrap line-clamp-3">{r.requirement}</p>
              </div>
              <Badge variant={r.classification === "KB" ? "success" : "muted"}>{r.classification}</Badge>
            </div>
          </CardContent>
        </Card>
      ))}
      {requirements?.length === 0 && (
        <p className="text-sm text-muted-foreground">No sections extracted for this tender yet.</p>
      )}
    </div>
  );
}

function BriefTab({ packId, documentText }: { packId: string; documentText: string }) {
  const [brief, setBrief] = useState<TenderBrief | null>(null);
  const gen = useMutation({
    mutationFn: () => tenderBrief(packId, documentText),
    onSuccess: setBrief,
  });
  return (
    <div className="space-y-4">
      <Button onClick={() => gen.mutate()} disabled={!documentText || gen.isPending}>
        <Sparkles className="size-4" /> {gen.isPending ? "Generating…" : "Generate tender brief"}
      </Button>
      {!documentText && <p className="text-sm text-muted-foreground">No tender document on file for this pack.</p>}
      {gen.isError && <p className="text-sm text-destructive">Could not generate a brief -- try again.</p>}
      {brief && (
        <Card>
          <CardContent className="pt-6 space-y-4 text-sm">
            <Section title="Summary" body={brief.summary} />
            <Section title="Scope" body={brief.scope} />
            <Section title="Submission format" body={brief.submission_format} />
            <ListSection title="Key dates" items={brief.key_dates} />
            <ListSection title="Success criteria" items={brief.success_criteria} />
            <ListSection title="Gaps & risks" items={brief.gaps_and_risks} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Section({ title, body }: { title: string; body: string }) {
  if (!body) return null;
  return <div><p className="font-semibold mb-1">{title}</p><p className="text-muted-foreground">{body}</p></div>;
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <p className="font-semibold mb-1">{title}</p>
      <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
        {items.map((i) => <li key={i}>{i}</li>)}
      </ul>
    </div>
  );
}

function ComplianceTab({ packId, documentText }: { packId: string; documentText: string }) {
  const [items, setItems] = useState<ComplianceItem[] | null>(null);
  const gen = useMutation({
    mutationFn: () => complianceCheck(packId, documentText),
    onSuccess: setItems,
  });
  return (
    <div className="space-y-4">
      <Button onClick={() => gen.mutate()} disabled={!documentText || gen.isPending}>
        <ShieldCheck className="size-4" /> {gen.isPending ? "Checking…" : "Run compliance check"}
      </Button>
      {!documentText && <p className="text-sm text-muted-foreground">No tender document on file for this pack.</p>}
      {gen.isError && <p className="text-sm text-destructive">Could not run the compliance check -- try again.</p>}
      {items?.map((it, idx) => (
        <Card key={idx}>
          <CardContent className="pt-4 pb-4 flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium">{it.requirement}</p>
              <p className="text-xs text-muted-foreground">{it.note}</p>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge variant="muted">{it.category}</Badge>
              <Badge variant={it.owner === "AI" ? "success" : "muted"}>{it.owner === "AI" ? "AI can draft" : "Needs a human"}</Badge>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ChatTab({ packId }: { packId: string }) {
  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<{ q: string; a: string }[]>([]);
  const ask = useMutation({
    mutationFn: () => askBidContext(packId, question),
    onSuccess: (res) => { setThread((t) => [...t, { q: question, a: res.answer }]); setQuestion(""); },
  });
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <MessageSquare className="size-4" /> Ask about this tender
      </div>
      <div className="space-y-3">
        {thread.map((t, i) => (
          <div key={i} className="space-y-1">
            <p className="text-sm font-medium">{t.q}</p>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{t.a}</p>
          </div>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); if (question.trim()) ask.mutate(); }} className="flex gap-2">
        <input value={question} onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What currency should the priced tender be submitted in?"
          className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <Button type="submit" disabled={ask.isPending || !question.trim()}>{ask.isPending ? "Asking…" : "Ask"}</Button>
      </form>
    </div>
  );
}

function ExportTab({ packId }: { packId: string }) {
  const options = [
    { kind: "xlsx" as const, label: "Answer sheet (.xlsx)", desc: "Requirement, answer, confidence, decision -- internal review format.", icon: FileText },
    { kind: "docx-clean" as const, label: "Client-ready submission (.docx)", desc: "Section headings + prose only, no confidence/citation clutter.", icon: FileCheck2 },
    { kind: "docx-review" as const, label: "Internal annotated (.docx)", desc: "Requirement text + confidence note + answer + KB citations.", icon: Layers },
  ];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {options.map((o) => (
        <a key={o.kind} href={exportUrl(packId, o.kind)} target="_blank" rel="noreferrer">
          <Card className="h-full transition-colors hover:border-primary/40">
            <CardContent className="pt-6 space-y-2">
              <o.icon className="size-5 text-primary" />
              <p className="text-sm font-semibold">{o.label}</p>
              <p className="text-xs text-muted-foreground">{o.desc}</p>
              <span className="inline-flex items-center gap-1 text-xs font-medium text-primary"><Download className="size-3.5" /> Download</span>
            </CardContent>
          </Card>
        </a>
      ))}
    </div>
  );
}
