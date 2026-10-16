"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { createSalesOpportunity, listAgents } from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { OpportunityForm, toCreatePayload, type OpportunityFormValues } from "@/components/sales-intelligence/opportunity-form";

export default function NewOpportunityPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  const create = useMutation({
    mutationFn: (values: OpportunityFormValues) => createSalesOpportunity(agentId, toCreatePayload(values)),
    onSuccess: () => {
      // Refresh the pipeline list, then return to it (mirrors Ali's create -> back-to-pipeline flow).
      qc.invalidateQueries({ queryKey: ["sales-opportunities", agentId] });
      router.push(`/studio/${agentId}/sales-intelligence/pipeline`);
    },
    onError: () => setError("Couldn't create that opportunity. Check the fields and try again."),
  });

  const backToPipeline = () => router.push(`/studio/${agentId}/sales-intelligence/pipeline`);

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="pipeline">
      <div className="mx-auto max-w-3xl space-y-5">
        <button onClick={backToPipeline}
          className="flex items-center gap-1.5 rounded-md px-1 text-sm text-slate-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300">
          <ArrowLeft className="size-4" /> Back to pipeline
        </button>

        <div>
          <h1 className="text-xl font-semibold text-foreground">Add an opportunity</h1>
          <p className="mt-1 text-[13px] text-slate-400">
            Manually capture a tender that wasn&apos;t scanned from a portal. Only the title is required.
          </p>
        </div>

        <OpportunityForm
          mode="create"
          submitting={create.isPending}
          error={error}
          onSubmit={(values) => { setError(null); create.mutate(values); }}
          onCancel={backToPipeline}
        />
      </div>
    </CockpitShell>
  );
}
