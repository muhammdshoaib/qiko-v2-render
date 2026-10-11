"use client";

import { useState } from "react";
import { Button, Input } from "@qiko/ui";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useCrm } from "@/lib/crm/store";
import { WORKFLOW_IDS } from "@/lib/crm/workflows";
import { toast } from "sonner";

export function CompleteTaskButton({ taskId }: { taskId: string }) {
  const crm = useCrm();
  const [open, setOpen] = useState(false);
  const [evidence, setEvidence] = useState("");
  const needsEvidence = taskId === WORKFLOW_IDS.stalledTask;

  if (!needsEvidence) {
    return (
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => {
          crm.completeTask(taskId);
          toast.success("Task marked done. History updated.");
        }}
      >
        Mark done
      </Button>
    );
  }

  return (
    <>
      <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
        Record outcome
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>What happened?</DialogTitle>
            <DialogDescription>
              A draft does not close this task. Record the outcome so CRM last activity can update.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="stall-evidence">Outcome</Label>
            <Input
              id="stall-evidence"
              value={evidence}
              onChange={(event) => setEvidence(event.target.value)}
              placeholder="e.g. Helena confirmed she will review the outline"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              type="button"
              onClick={() => {
                const message = crm.completeStalledFollowUp(evidence);
                if (message.startsWith("Record what happened")) {
                  toast.error(message);
                  return;
                }
                toast.message(message);
                setOpen(false);
                setEvidence("");
              }}
            >
              Close with evidence
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
