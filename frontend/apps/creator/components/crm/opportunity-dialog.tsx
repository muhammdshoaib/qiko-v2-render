"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { Button, Input } from "@qiko/ui";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { OWNERS } from "@/lib/crm/seed";
import { useCrm } from "@/lib/crm/store";
import { PIPELINE_STAGES, STAGE_LABEL, type Opportunity, type PipelineStage } from "@/lib/crm/types";
import { toast } from "sonner";

export function OpportunityDialog({
  open,
  onOpenChange,
  initial,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial?: Opportunity | null;
}) {
  const crm = useCrm();
  const [companyId, setCompanyId] = useState(initial?.companyId ?? crm.companies[0]?.id ?? "");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [value, setValue] = useState(String(initial?.value ?? 25000));
  const [owner, setOwner] = useState<string>(initial?.owner ?? OWNERS[0]);
  const [stage, setStage] = useState<PipelineStage>(initial?.stage ?? "cold_lead");
  const [nextStep, setNextStep] = useState(initial?.nextStep ?? "");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !companyId) {
      toast.error("Company and title are required.");
      return;
    }
    crm.saveOpportunity({
      id: initial?.id ?? `o-${crypto.randomUUID().slice(0, 8)}`,
      companyId,
      title: title.trim(),
      value: Number(value) || 0,
      expectedRevenue: Math.round((Number(value) || 0) * 0.75),
      owner,
      stage,
      nextStep: nextStep.trim() || "Set next step",
    });
    toast.success(initial ? "Opportunity updated." : "Opportunity created.");
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#0c111c] text-slate-200">
        <DialogHeader>
          <DialogTitle>{initial ? "Edit opportunity" : "New opportunity"}</DialogTitle>
          <DialogDescription>Stored only in this browser. No CRM backend is called.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Company">
            <select className={selectClass} value={companyId} onChange={(event) => setCompanyId(event.target.value)}>
              {crm.companies.map((company) => (
                <option key={company.id} value={company.id}>{company.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Title">
            <Input value={title} onChange={(event) => setTitle(event.target.value)} required />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Value (GBP)">
              <Input type="number" min={0} value={value} onChange={(event) => setValue(event.target.value)} />
            </Field>
            <Field label="Owner">
              <select className={selectClass} value={owner} onChange={(event) => setOwner(event.target.value)}>
                {OWNERS.map((name) => <option key={name}>{name}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Stage">
            <select className={selectClass} value={stage} onChange={(event) => setStage(event.target.value as PipelineStage)}>
              {PIPELINE_STAGES.map((item) => <option key={item} value={item}>{STAGE_LABEL[item]}</option>)}
            </select>
          </Field>
          <Field label="Next step">
            <Input value={nextStep} onChange={(event) => setNextStep(event.target.value)} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit">{initial ? "Save changes" : "Create opportunity"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

const selectClass = "flex h-11 w-full rounded-md border border-input bg-background px-3 text-sm";
