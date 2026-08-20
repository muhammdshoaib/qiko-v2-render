"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Loader2, Search } from "lucide-react";
import { Badge, Button } from "@qiko/ui";
import {
  acceptResearchRun,
  createResearchRun,
  getResearchRun,
  type BriefOut,
  type ResearchRunOut,
} from "@/lib/api";

const STAGES = ["scout", "specialists", "synthesize", "critic", "magistrate"] as const;

function stageLabel(stage: string) {
  if (stage === "specialists") return "Specialists";
  return stage.charAt(0).toUpperCase() + stage.slice(1);
}

function statusVariant(status: string | undefined) {
  if (status === "ready") return "success";
  if (status === "in_progress") return "warning";
  if (status === "error") return "destructive";
  return "muted";
}

export function ResearchTab({ agentId }: { agentId: string }) {
  const qc = useQueryClient();
  const [subject, setSubject] = useState("");
  const [facetsText, setFacetsText] = useState("");
  const [runId, setRunId] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => {
      const facets = facetsText
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      return createResearchRun(agentId, { subject: subject.trim(), facets });
    },
    onSuccess: (data) => setRunId(data.run_id),
  });

  const run = useQuery<ResearchRunOut>({
    queryKey: ["research-run", agentId, runId],
    queryFn: () => getResearchRun(agentId, runId!),
    enabled: !!runId,
  });

  useEffect(() => {
    if (!runId) return;
    if (run.data?.brief && run.data.brief.status !== "in_progress") return;
    const id = setInterval(() => run.refetch(), 2000);
    return () => clearInterval(id);
  }, [runId, run.data?.brief?.status, run.refetch]);

  const accept = useMutation({
    mutationFn: () => acceptResearchRun(agentId, runId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["research-run", agentId, runId] }),
  });

  const running = !!runId && (!run.data?.brief || run.data.brief.status === "in_progress");

  return (
    <section className="space-y-6 text-white">
      <div>
        <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
          <Search className="size-4 text-primary" /> Research
        </h2>
        <p className="text-xs text-white/50">
          Give the worker a subject and facets to research over the ingested evidence.
        </p>
      </div>

      {!runId && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (subject.trim() && !create.isPending) create.mutate();
          }}
          className="space-y-4 rounded-xl border border-white/[0.08] bg-white/[0.03] p-4"
        >
          <div className="space-y-2">
            <label className="text-sm font-medium text-white/70" htmlFor="subject">
              Subject
            </label>
            <input
              id="subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. Acme Corp"
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/40 outline-none focus:border-indigo-400/45"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-white/70" htmlFor="facets">
              Facets (comma or newline separated)
            </label>
            <textarea
              id="facets"
              value={facetsText}
              onChange={(e) => setFacetsText(e.target.value)}
              placeholder="What do they do?, Who are the people?, What is unresolved?, What looks risky?"
              rows={3}
              className="w-full rounded-lg border border-white/[0.08] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/40 outline-none focus:border-indigo-400/45"
            />
          </div>
          <Button type="submit" disabled={!subject.trim() || create.isPending} className="w-full sm:w-auto">
            {create.isPending && <Loader2 className="size-4 animate-spin" />}
            Start research
          </Button>
          {create.isError && <p className="text-sm text-rose-400">Could not start research.</p>}
        </form>
      )}

      {runId && (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => setRunId(null)}
            className="text-sm text-white/50 hover:text-white"
          >
            Start new research
          </button>
          {run.isLoading && <p className="text-sm text-white/50">Loading run...</p>}
          {run.isError && <p className="text-sm text-rose-400">Could not load research run.</p>}
          {run.data && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-white/70">
                  Run <span className="font-mono text-white">{run.data.run_id.slice(0, 8)}</span>
                </p>
                {running ? (
                  <Badge variant="warning" dot>
                    Running
                  </Badge>
                ) : (
                  <Badge variant="success">Done</Badge>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                {STAGES.map((stage) => {
                  const status =
                    typeof run.data!.status === "object"
                      ? (run.data!.status[stage] as string | undefined)
                      : undefined;
                  return (
                    <div
                      key={stage}
                      className="rounded-lg border border-white/[0.08] bg-white/[0.03] p-3"
                    >
                      <p className="text-xs font-medium text-white/50">{stageLabel(stage)}</p>
                      <Badge variant={statusVariant(status)} className="mt-1 capitalize">
                        {status ?? "pending"}
                      </Badge>
                    </div>
                  );
                })}
              </div>
              {run.data.brief && run.data.brief.status !== "in_progress" && (
                <BriefCard
                  brief={run.data.brief}
                  onAccept={
                    run.data.brief.status === "draft" ? () => accept.mutate() : undefined
                  }
                  accepting={accept.isPending}
                />
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function BriefCard({
  brief,
  onAccept,
  accepting,
}: {
  brief: BriefOut;
  onAccept?: () => void;
  accepting?: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white">Brief</h3>
          <Badge variant={brief.status === "accepted" ? "success" : "warning"} className="mt-1 capitalize">
            {brief.status}
          </Badge>
        </div>
        {onAccept && (
          <Button onClick={onAccept} disabled={accepting} size="sm">
            {accepting ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
            Accept
          </Button>
        )}
      </div>
      <p className="text-sm leading-relaxed text-white/80">{brief.summary}</p>
      {brief.findings.length > 0 && (
        <div className="mt-4 space-y-3">
          <p className="text-xs font-medium uppercase tracking-wide text-white/40">Findings</p>
          {brief.findings.map((f, i) => (
            <div key={i} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
              <p className="text-sm text-white/90">{f.text}</p>
              {f.evidence_refs.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {f.evidence_refs.map((ref) => (
                    <span
                      key={ref}
                      className="rounded bg-white/[0.06] px-2 py-0.5 text-xs text-white/60"
                    >
                      {ref}
                    </span>
                  ))}
                </div>
              )}
              {f.gaps && <p className="mt-2 text-xs text-amber-300/80">Gap: {f.gaps}</p>}
            </div>
          ))}
        </div>
      )}
      {brief.gaps && (
        <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3">
          <p className="flex items-center gap-2 text-xs font-medium text-amber-300">
            <AlertTriangle className="size-4" /> Gaps
          </p>
          <p className="mt-1 text-sm text-amber-100/80">{brief.gaps}</p>
        </div>
      )}
      {brief.citations.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {brief.citations.map((c) => (
            <span
              key={c}
              className="rounded bg-white/[0.06] px-2 py-0.5 text-xs text-white/60"
            >
              {c}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
