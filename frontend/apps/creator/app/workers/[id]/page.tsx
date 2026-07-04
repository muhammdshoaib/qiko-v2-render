"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileText, Trash2 } from "lucide-react";
import { Badge, Button, Card, CardContent, Input, Label, Skeleton, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import {
  addBehavior, addFaq, addPolicy, addWebsite,
  deleteDocument, ingest, listDocuments, type Doc,
} from "@/lib/api";

const TABS = ["Knowledge", "Behaviors", "FAQs", "Websites", "Policies"] as const;
type Tab = (typeof TABS)[number];

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className="min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />;
}

export default function WorkerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("Knowledge");
  const docs = useQuery({ queryKey: ["documents"], queryFn: listDocuments });
  const refresh = () => qc.invalidateQueries({ queryKey: ["documents"] });

  return (
    <AppShell title="Worker">
      <div className="mx-auto max-w-3xl space-y-6">
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to workers
        </Link>

        <div className="flex gap-1 border-b border-border">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={cn("border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
              {t}
            </button>
          ))}
        </div>

        {tab === "Knowledge" && <KnowledgeTab id={id} docs={docs.data} loading={docs.isLoading} onChange={refresh} />}
        {tab === "Behaviors" && (
          <SourceForm title="Add a behavior" onSubmit={(sid) => addBehavior(id, sid, val("behavior"))} fields={[["behavior", "Behavior", true]]} onDone={refresh} />
        )}
        {tab === "FAQs" && (
          <SourceForm title="Add an FAQ" onSubmit={(sid) => addFaq(id, sid, val("q"), val("a"))} fields={[["q", "Question", false], ["a", "Answer", true]]} onDone={refresh} />
        )}
        {tab === "Websites" && (
          <SourceForm title="Add a website" onSubmit={(sid) => addWebsite(id, sid, val("name"), val("url"), val("details"))} fields={[["name", "Name", false], ["url", "URL", false], ["details", "Details", true]]} onDone={refresh} />
        )}
        {tab === "Policies" && (
          <SourceForm title="Add a policy" onSubmit={(sid) => addPolicy(id, sid, val("title"), val("body"))} fields={[["title", "Title", false], ["body", "Body", true]]} onDone={refresh} />
        )}
      </div>
    </AppShell>
  );

  // simple field-value store scoped per render via DOM ids
  function val(name: string): string {
    return (document.getElementById(`f-${name}`) as HTMLInputElement | HTMLTextAreaElement | null)?.value ?? "";
  }
}

function KnowledgeTab({ id, docs, loading, onChange }: { id: string; docs?: Doc[]; loading: boolean; onChange: () => void }) {
  const [text, setText] = useState("");
  const add = useMutation({ mutationFn: () => ingest(`${id}-${Date.now()}`, text), onSuccess: () => { setText(""); onChange(); } });
  const remove = useMutation({ mutationFn: (d: string) => deleteDocument(d), onSuccess: onChange });
  return (
    <div className="space-y-4">
      <Card><CardContent className="space-y-3 pt-6">
        <Textarea id="f-knowledge" placeholder="Add free-text knowledge…" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="flex justify-end"><Button disabled={!text.trim() || add.isPending} onClick={() => add.mutate()}>Add knowledge</Button></div>
      </CardContent></Card>
      <div className="space-y-2">
        {loading && [0, 1].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        {docs?.map((d) => (
          <Card key={d.doc_id}><CardContent className="flex items-center justify-between py-3">
            <div className="flex items-center gap-3"><FileText className="size-4 text-muted-foreground" />
              <span className="text-sm font-medium">{d.doc_id}</span><Badge variant="muted">{d.chunks}</Badge></div>
            <Button variant="ghost" size="icon" onClick={() => remove.mutate(d.doc_id)}><Trash2 className="size-4 text-muted-foreground" /></Button>
          </CardContent></Card>
        ))}
        {docs?.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No documents yet.</p>}
      </div>
    </div>
  );
}

function SourceForm({ title, fields, onSubmit, onDone }: {
  title: string;
  fields: [string, string, boolean][];
  onSubmit: (sourceId: string) => Promise<unknown>;
  onDone: () => void;
}) {
  const m = useMutation({ mutationFn: () => onSubmit(`${Date.now()}`), onSuccess: onDone });
  return (
    <Card><CardContent className="space-y-3 pt-6">
      <p className="font-medium">{title}</p>
      {fields.map(([name, label, area]) => (
        <div key={name} className="space-y-1.5">
          <Label htmlFor={`f-${name}`}>{label}</Label>
          {area ? <Textarea id={`f-${name}`} /> : <Input id={`f-${name}`} />}
        </div>
      ))}
      {m.isError && <p className="text-sm text-destructive">Not permitted (needs editor role).</p>}
      {m.isSuccess && <p className="text-sm text-success">Added — grounding updated.</p>}
      <div className="flex justify-end"><Button disabled={m.isPending} onClick={() => m.mutate()}>Save</Button></div>
    </CardContent></Card>
  );
}
