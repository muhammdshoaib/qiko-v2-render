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
  intelligence: "intelligence",
};

export function StudioWorkerRouteGuard({ children }: { children: ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const access = useQuery({
    // Keyed on the worker only. The request is listAgents(), which does not depend on the route,
    // and keying on pathname too gave every tab inside a cockpit its own cache entry -- so moving
    // from /studio/:id/finance to /finance/history was a cache miss and blanked the whole screen
    // on a worker the user was already cleared for. The pathname is still used below, for the
    // redirect and type-match checks, but those are derived from this data rather than fetched.
    queryKey: ["studio-worker-access", id],
    queryFn: async () => (await listAgents()).find((candidate) => candidate.id === id) ?? null,
    refetchOnMount: "always",
    staleTime: 0,
  });
  const worker = access.data;

  // isPending only: "no data yet", which is the one case that has to block. isFetching is also
  // true for the background revalidation this query does on every mount, and gating on it replaced
  // a cockpit that had everything it needed with a full-screen spinner. The cost is that children
  // render from cache while that revalidation is in flight, so a worker disabled mid-session keeps
  // its cockpit for one request before this flips to Worker unavailable. Server-side authorization
  // rejects the API calls from it either way, so that window is cosmetic.
  if (access.isPending) {
    return (
      <div role="status" aria-live="polite" aria-busy="true" className="flex min-h-screen items-center justify-center bg-background text-slate-400">
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

  // A bare /studio/:id URL is valid for the generic worker page, but verticals must
  // redirect to their cockpit so the Studio grid can link to /studio/:id for all workers.
  if (worker && worker.enabled !== false && worker.status === "ready" && segment && expectedPath && pathname === `/studio/${id}`) {
    router.replace(expectedPath);
    return null;
  }

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
    <div role="alert" aria-live="assertive" className="flex min-h-screen items-center justify-center bg-background px-4 text-slate-700">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-muted/50 p-6 text-center shadow-2xl">
        <span className="mx-auto mb-4 grid size-11 place-items-center rounded-xl bg-amber-50 text-amber-300">
          <AlertTriangle className="size-5" aria-hidden="true" />
        </span>
        <h1 className="text-lg font-semibold text-foreground">{message}</h1>
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
