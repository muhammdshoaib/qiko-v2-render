"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { setPackOutcome, type RfpPack } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  LOSS_REASONS,
  MAX_OUTCOME_VALUE,
  buildOutcomePayload,
  outcomeDraftIsValid,
  type OutcomeDraft,
} from "@/components/pre-sales/outcome-utils";

const OUTCOMES: { value: OutcomeDraft; label: string; description: string }[] = [
  { value: "pending", label: "Pending", description: "Keep this bid active." },
  { value: "won", label: "Won", description: "Record a successful bid." },
  { value: "lost", label: "Lost", description: "Record a loss and its reason." },
  { value: "withdrawn", label: "Withdrawn", description: "Close without a win or loss." },
];

const LOSS_REASON_LABELS: Record<(typeof LOSS_REASONS)[number], string> = {
  price: "Price",
  technical: "Technical fit",
  relationship: "Relationship",
  timeline: "Timeline",
  no_bid_decision: "No-bid decision",
  other: "Other",
};

export function OutcomeDialog({ pack, agentId, open, onOpenChange }: {
  pack: RfpPack;
  agentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [outcome, setOutcome] = useState<OutcomeDraft>(pack.outcome ?? "pending");
  const [reason, setReason] = useState(pack.outcome_reason ?? "");
  const [value, setValue] = useState(pack.outcome_value === null ? "" : String(pack.outcome_value));

  useEffect(() => {
    if (!open) return;
    setOutcome(pack.outcome ?? "pending");
    setReason(pack.outcome_reason ?? "");
    setValue(pack.outcome_value === null ? "" : String(pack.outcome_value));
  }, [open, pack]);

  const save = useMutation({
    mutationFn: () => {
      const payload = buildOutcomePayload(outcome, reason, value);
      return setPackOutcome(pack.id, payload.outcome, payload.reason, payload.value);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<RfpPack[]>(["rfp-packs", agentId], (previous) =>
        previous?.map((item) => item.id === updated.id ? updated : item));
      queryClient.invalidateQueries({ queryKey: ["rfp-packs", agentId] });
      onOpenChange(false);
    },
  });

  const valid = outcomeDraftIsValid(outcome, reason, value);
  const original = JSON.stringify({
    outcome: pack.outcome,
    reason: pack.outcome === "lost" ? pack.outcome_reason : "",
    value: pack.outcome_value,
  });
  const changed = valid && JSON.stringify(buildOutcomePayload(outcome, reason, value)) !== original;

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!save.isPending) onOpenChange(next); }}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto border-white/10 bg-[#0a0d15] text-slate-100 sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Update outcome for {pack.title}</DialogTitle>
          <DialogDescription>
            Review the status for {pack.title} before confirming. This updates reporting and active bid metrics.
          </DialogDescription>
        </DialogHeader>

        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-medium text-slate-200">Outcome</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {OUTCOMES.map((option) => (
              <label key={option.value} className={`flex min-h-14 cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors ${outcome === option.value ? "border-cyan-400/60 bg-cyan-400/10" : "border-white/10 bg-white/[0.02] hover:bg-white/[0.04]"}`}>
                <input
                  type="radio"
                  name="tender-outcome"
                  value={option.value}
                  checked={outcome === option.value}
                  onChange={() => setOutcome(option.value)}
                  className="mt-1 size-4 accent-cyan-400"
                />
                <span>
                  <span className="block text-sm font-semibold text-white">{option.label}</span>
                  <span className="block text-xs leading-5 text-slate-400">{option.description}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {outcome === "lost" && (
          <div className="space-y-2">
            <Label htmlFor="loss-reason">Loss reason</Label>
            <select
              id="loss-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className="min-h-11 w-full rounded-md border border-white/10 bg-[#0f131d] px-3 text-sm text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
              required
            >
              <option value="">Select a reason</option>
              {LOSS_REASONS.map((item) => <option key={item} value={item}>{LOSS_REASON_LABELS[item]}</option>)}
            </select>
            {!reason && <p className="text-xs text-amber-300">A reason is required for lost bids.</p>}
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="outcome-value">Tender value</Label>
          <Input
            id="outcome-value"
            type="number"
            min="0"
            max={MAX_OUTCOME_VALUE}
            step="0.01"
            inputMode="decimal"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Leave empty when no value is recorded"
          />
          <p className="text-xs text-slate-400">Existing value is preserved unless you edit or clear this field.</p>
        </div>

        {save.isError && (
          <p role="alert" className="rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-300">
            We couldn&apos;t update this outcome. Review the details and try again.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={save.isPending}>Cancel</Button>
          <Button onClick={() => save.mutate()} disabled={!changed || save.isPending}>
            {save.isPending && <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />}
            Confirm outcome
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
