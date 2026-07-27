"use client";

import type { ReactNode } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, RotateCw } from "lucide-react";
import { Button } from "@qiko/ui";
import { listAgents } from "@/lib/api";

const TYPE_SEGMENTS: Record<string, string | null> = {
  worker: null,
  pre_sales_writer: "pre-sales",
  finance: "finance",
  sales_intelligence: "sales-intelligence",
};

export function StudioWorkerRouteGuard({ children }: { children: ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const access = useQuery({
    queryKey: ["studio-worker-access", id, pathname],
    queryFn: async () => (await listAgents()).find((candidate) => candidate.id === id) ?? null,
    refetchOnMount: "always",
    staleTime: 0,
  });
  const worker = access.data;

  if (access.isPending || access.isFetching) {
    return (
      <div role="status" aria-live="polite" aria-busy="true" className="flex min-h-screen items-center justify-center bg-[#050810] text-slate-400">
        <Loader2 className="size-5 animate-spin" aria-hidden="true" />
        <span className="ml-2 text-sm">Checking worker availability...</span>
      </div>
    );
  }

  if (access.isError) {
    return (
      <UnavailableState
        message="We couldn't verify this worker right now."
        actionLabel="Try again"
        onAction={() => access.refetch()}
        retry
      />
    );
  }

  const segment = worker ? TYPE_SEGMENTS[worker.atype] : undefined;
  const expectedPath = segment === null ? `/studio/${id}` : segment ? `/studio/${id}/${segment}` : null;
  const typeMatches = expectedPath !== null
    && (segment === null ? pathname === expectedPath : pathname.startsWith(expectedPath));

  if (!worker || worker.enabled === false || worker.status !== "ready" || !typeMatches) {
    return (
      <UnavailableState
        message="Worker unavailable"
        actionLabel="Back to Studio"
        onAction={() => router.replace("/studio")}
      />
    );
  }

  return children;
}

function UnavailableState({ message, actionLabel, onAction, retry = false }: {
  message: string;
  actionLabel: string;
  onAction: () => void;
  retry?: boolean;
}) {
  return (
    <div role="alert" aria-live="assertive" className="flex min-h-screen items-center justify-center bg-[#050810] px-4 text-slate-200">
      <div className="w-full max-w-sm rounded-2xl border border-white/[0.08] bg-white/[0.02] p-6 text-center shadow-2xl">
        <span className="mx-auto mb-4 grid size-11 place-items-center rounded-xl bg-amber-500/10 text-amber-300">
          <AlertTriangle className="size-5" aria-hidden="true" />
        </span>
        <h1 className="text-lg font-semibold text-white">{message}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          This worker cannot be opened from this link. Return to Studio and choose an available worker.
        </p>
        <Button className="mt-5 min-h-11 w-full" onClick={onAction}>
          {retry && <RotateCw className="mr-2 size-4" aria-hidden="true" />}
          {actionLabel}
        </Button>
      </div>
    </div>
  );
}
