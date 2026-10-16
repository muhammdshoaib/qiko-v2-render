"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  BarChart3,
  Calendar,
  ChevronDown,
  ChevronRight,
  Filter,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { Badge, Checkbox, cn, Select } from "@qiko/ui";
import {
  getDiscrepancies,
  getDiscrepancyDigest,
  updateAgentConfig,
  type Agent,
  type DiscrepanciesResponse,
  type Discrepancy,
  type DiscrepancyDigest,
  type IntelligenceMetrics,
} from "@/lib/api";

const LIMIT = 25;

const BG = "#050810";

function useDiscrepancyProjects(worker: Agent | undefined, metrics: IntelligenceMetrics | undefined) {
  return useMemo(() => {
    const keys = new Set<string>();
    if (metrics?.projects) Object.keys(metrics.projects).forEach((k) => keys.add(k));
    const active = (worker?.config?.discrepancy_active_projects as string[] | undefined) ?? [];
    return { available: Array.from(keys).sort(), active };
  }, [worker, metrics]);
}

export function DiscrepanciesTab({
  agentId,
  worker,
  metrics,
}: {
  agentId: string;
  worker: Agent | undefined;
  metrics: IntelligenceMetrics | undefined;
}) {
  const queryClient = useQueryClient();
  const { available, active } = useDiscrepancyProjects(worker, metrics);
  const [selectedProjects, setSelectedProjects] = useState<string[]>(active);
  const [view, setView] = useState<"list" | "digest">("list");
  const [digestWindow, setDigestWindow] = useState<"daily" | "weekly">(
    (worker?.config?.discrepancy_digest_frequency as "daily" | "weekly" | undefined) ?? "daily"
  );
  const [page, setPage] = useState(0);
  const [expandedClasses, setExpandedClasses] = useState<Set<string>>(new Set());

  useEffect(() => {
    setSelectedProjects(active.length > 0 ? active : available);
    const saved = worker?.config?.discrepancy_digest_frequency as "daily" | "weekly" | undefined;
    if (saved) setDigestWindow(saved);
  }, [worker, available]);

  const saveConfig = useMutation({
    mutationFn: (patch: Record<string, unknown>) => updateAgentConfig(agentId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  const discrepancies = useQuery({
    queryKey: ["intelligence-discrepancies", agentId, selectedProjects, page],
    queryFn: () =>
      getDiscrepancies(agentId, {
        project: selectedProjects.length > 0 ? selectedProjects : undefined,
        limit: LIMIT,
        offset: page * LIMIT,
      }),
  });

  const digest = useQuery({
    queryKey: ["intelligence-discrepancy-digest", agentId, digestWindow, selectedProjects],
    queryFn: () => getDiscrepancyDigest(agentId, digestWindow, selectedProjects.length > 0 ? selectedProjects : undefined),
    enabled: view === "digest",
  });

  const data: DiscrepanciesResponse | undefined = discrepancies.data;
  const byClass = useMemo(() => {
    const map = new Map<string, Discrepancy[]>();
    if (!data) return map;
    for (const d of data.items) {
      map.set(d.class, [...(map.get(d.class) ?? []), d]);
    }
    return map;
  }, [data]);

  const projectOptions = useMemo(
    () => (available.length > 0 ? available : (data?.projects.map((p) => p.project_key ?? "_other") ?? [])),
    [available, data]
  );
  const allProjectsSelected = projectOptions.length > 0 && projectOptions.every((p) => selectedProjects.includes(p));

  useEffect(() => {
    if (selectedProjects.length === 0 && projectOptions.length > 0) {
      setSelectedProjects(projectOptions);
    }
  }, [projectOptions]);

  const toggleProject = (key: string) => {
    const next = selectedProjects.includes(key)
      ? selectedProjects.filter((p) => p !== key)
      : [...selectedProjects, key];
    setSelectedProjects(next);
    setPage(0);
    saveConfig.mutate({ discrepancy_active_projects: next });
  };

  const toggleAllProjects = () => {
    const next = allProjectsSelected ? [] : projectOptions.slice();
    setSelectedProjects(next);
    setPage(0);
    saveConfig.mutate({ discrepancy_active_projects: next });
  };

  const toggleClass = (cls: string) => {
    const next = new Set(expandedClasses);
    if (next.has(cls)) next.delete(cls);
    else next.add(cls);
    setExpandedClasses(next);
  };

  const onDigestWindowChange = (value: "daily" | "weekly") => {
    setDigestWindow(value);
    saveConfig.mutate({ discrepancy_digest_frequency: value });
  };

  const severityCounts = useMemo(() => {
    const counts = { high: 0, medium: 0, low: 0 };
    if (!data) return counts;
    for (const d of data.items) counts[d.severity] += 1;
    return counts;
  }, [data]);

  return (
    <section className="space-y-4" style={{ background: BG }}>
      <SummaryPanel
        total={data?.total ?? 0}
        severityCounts={severityCounts}
        projectCounts={data?.projects ?? []}
      />

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-muted p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs font-medium text-foreground/70">
            <Filter className="size-3.5" /> Active projects
          </span>
          {projectOptions.length === 0 && (
            <span className="text-xs text-slate-400">No projects available</span>
          )}
          {projectOptions.map((key) => (
            <label
              key={key}
              className={cn(
                "flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
                selectedProjects.includes(key)
                  ? "border-indigo-300 bg-indigo-50 text-indigo-800"
                  : "border-border bg-muted text-slate-500 hover:text-foreground"
              )}
            >
              <Checkbox
                checked={selectedProjects.includes(key)}
                onChange={() => toggleProject(key)}
                className="size-3"
              />
              {key === "_other" ? "Other" : key}
            </label>
          ))}
          {projectOptions.length > 0 && (
            <button onClick={toggleAllProjects} className="text-xs text-primary hover:underline">
              {allProjectsSelected ? "Clear" : "Select all"}
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setView("list")}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              view === "list" ? "bg-slate-100 text-foreground" : "text-slate-500 hover:text-foreground"
            )}
          >
            List
          </button>
          <button
            onClick={() => setView("digest")}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              view === "digest" ? "bg-slate-100 text-foreground" : "text-slate-500 hover:text-foreground"
            )}
          >
            Heads-up digest
          </button>
        </div>
      </div>

      {view === "digest" && (
        <div className="rounded-xl border border-border bg-muted p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Calendar className="size-4 text-primary" /> {digestWindow === "daily" ? "Daily" : "Weekly"} digest
            </h2>
            <div className="flex items-center gap-2">
              <Select
                value={digestWindow}
                onChange={(e) => onDigestWindowChange(e.target.value as "daily" | "weekly")}
                className="rounded-md border border-border bg-slate-50 px-2 py-1 text-xs text-foreground"
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </Select>
              <button onClick={() => digest.refetch()} className="text-slate-500 hover:text-foreground" aria-label="Refresh digest">
                <RefreshCw className={cn("size-4", digest.isFetching && "animate-spin")} />
              </button>
            </div>
          </div>
          <DigestView digest={digest.data} loading={digest.isLoading} error={digest.isError} />
        </div>
      )}

      {view === "list" && (
        <>
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <ShieldAlert className="size-4 text-amber-700" /> Open discrepancies
              {data && <Badge variant="muted">{data.total}</Badge>}
            </h2>
            <button onClick={() => discrepancies.refetch()} className="text-slate-500 hover:text-foreground" aria-label="Refresh discrepancies">
              <RefreshCw className={cn("size-4", discrepancies.isFetching && "animate-spin")} />
            </button>
          </div>

          {discrepancies.isLoading && <PageSkeleton />}

          {!discrepancies.isLoading && (data?.items.length ?? 0) === 0 && (
            <EmptyState />
          )}

          {data && data.items.length > 0 && (
            <div className="space-y-3">
              {Array.from(byClass.entries()).map(([cls, items]) => {
                const expanded = expandedClasses.has(cls);
                const counts = { high: 0, medium: 0, low: 0 };
                for (const d of items) counts[d.severity] += 1;
                return (
                  <div key={cls} className="rounded-xl border border-border bg-muted p-3">
                    <button
                      onClick={() => toggleClass(cls)}
                      className="flex w-full items-center justify-between gap-3"
                    >
                      <div className="flex flex-1 items-center gap-3">
                        {expanded ? <ChevronDown className="size-4 text-slate-500" /> : <ChevronRight className="size-4 text-slate-500" />}
                        <span className="text-sm font-medium text-foreground">{items[0]?.class_label ?? cls.replace(/_/g, " ")}</span>
                        <Badge variant="muted">{items.length}</Badge>
                        <SeverityBar counts={counts} total={items.length} />
                      </div>
                    </button>
                    {expanded && (
                      <div className="mt-3 space-y-2">
                        {items.map((d, idx) => (
                          <DiscrepancyCard key={`${cls}-${idx}`} discrepancy={d} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {data && data.total > LIMIT && (
            <div className="flex items-center justify-between pt-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-foreground/70 hover:bg-slate-50 disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-xs text-slate-500">
                Page {page + 1} of {Math.max(1, Math.ceil(data.total / LIMIT))}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={(page + 1) * LIMIT >= data.total}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-foreground/70 hover:bg-slate-50 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function SummaryPanel({
  total,
  severityCounts,
  projectCounts,
}: {
  total: number;
  severityCounts: { high: number; medium: number; low: number };
  projectCounts: { project_key: string | null; count: number }[];
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="rounded-xl border border-border bg-muted p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <BarChart3 className="size-4 text-primary" /> Discrepancy overview
        </div>
        <div className="flex items-end gap-4">
          <div className="text-3xl font-bold text-foreground">{total}</div>
          <div className="flex-1 space-y-2 pb-1">
            <SeverityBar counts={severityCounts} total={total} showLegend />
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-muted p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <ShieldAlert className="size-4 text-amber-700" /> By project
        </div>
        <div className="flex flex-wrap gap-2">
          {projectCounts.length === 0 && <span className="text-xs text-slate-400">No project data</span>}
          {projectCounts.slice(0, 8).map((p) => (
            <div
              key={p.project_key ?? "other"}
              className="flex items-center gap-1.5 rounded-md bg-slate-50 px-2 py-1 text-xs text-slate-700"
            >
              <span className="font-medium">{p.project_key ?? "Other"}</span>
              <span className="text-slate-500">{p.count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SeverityBar({
  counts,
  total,
  showLegend = false,
}: {
  counts: { high: number; medium: number; low: number };
  total: number;
  showLegend?: boolean;
}) {
  if (total === 0) return <div className="h-2 w-full rounded-full bg-slate-50" />;
  const high = (counts.high / total) * 100;
  const medium = (counts.medium / total) * 100;
  const low = 100 - high - medium;
  return (
    <div className="flex flex-1 flex-col gap-1">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-50">
        {high > 0 && <div className="h-full bg-rose-500" style={{ width: `${high}%` }} />}
        {medium > 0 && <div className="h-full bg-amber-400" style={{ width: `${medium}%` }} />}
        {low > 0 && <div className="h-full bg-slate-400" style={{ width: `${low}%` }} />}
      </div>
      {showLegend && (
        <div className="flex gap-3 text-[10px] text-slate-400">
          <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-rose-500" /> High {counts.high}</span>
          <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-amber-400" /> Medium {counts.medium}</span>
          <span className="flex items-center gap-1"><span className="size-1.5 rounded-full bg-slate-400" /> Low {counts.low}</span>
        </div>
      )}
    </div>
  );
}

function DiscrepancyCard({ discrepancy: d }: { discrepancy: Discrepancy }) {
  return (
    <div className="rounded-xl border border-border bg-muted p-4 text-sm text-slate-700">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span
            className={cn(
              "mt-1.5 size-2 shrink-0 rounded-full",
              d.severity === "high" ? "bg-rose-500" : d.severity === "medium" ? "bg-amber-400" : "bg-slate-400"
            )}
            aria-hidden="true"
          />
          <p className="font-medium text-foreground">{d.title}</p>
        </div>
        {d.ref && (
          <span className="shrink-0 rounded bg-muted px-2 py-0.5 text-xs text-slate-600">{d.ref}</span>
        )}
      </div>
      <p className="mb-3 leading-relaxed text-slate-500">{d.summary}</p>
      {d.sources.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {d.sources.map((s, i) => {
            const label = [s.source_label, s.actor && `by ${s.actor}`, formatDate(s.occurred_at)].filter(Boolean).join(" ");
            return s.url ? (
              <a
                key={i}
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded bg-muted px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 hover:text-foreground"
              >
                {label}
              </a>
            ) : (
              <span key={i} className="inline-flex items-center gap-1 rounded bg-muted px-2 py-1 text-xs text-slate-600">
                {label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DigestView({
  digest,
  loading,
  error,
}: {
  digest: DiscrepancyDigest | undefined;
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <PageSkeleton />;
  if (error) return <p className="text-sm text-slate-500">The digest could not be generated. Please try again.</p>;
  if (!digest) return null;
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-foreground">{digest.headline}</h3>
        <p className="text-sm text-slate-600">{digest.summary}</p>
      </div>
      {digest.sections.length === 0 && <p className="text-sm text-slate-500">No open discrepancies for this window.</p>}
      {digest.sections.map((section, i) => (
        <div key={i} className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{section.title}</p>
          <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
            {section.items.map((item, j) => (
              <li key={j}>{item}</li>
            ))}
          </ul>
        </div>
      ))}
      {digest.tone !== "calm" && (
        <p className="text-xs text-slate-500">Tone: {digest.tone}</p>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-border bg-muted p-6 text-center">
      <p className="text-sm font-medium text-foreground">No open discrepancies</p>
      <p className="mt-1 text-xs text-slate-500">Adjust filters or connect Slack, Qiko Track or GitHub to start surfacing claim-vs-evidence gaps.</p>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-50" />
      ))}
    </div>
  );
}

function formatDate(value: string | null) {
  if (!value) return null;
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
