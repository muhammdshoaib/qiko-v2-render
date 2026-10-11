"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { Button, Input } from "@qiko/ui";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { OWNERS } from "@/lib/crm/seed";
import { formatDate } from "@/lib/crm/format";
import { useCrm } from "@/lib/crm/store";
import type { TaskPriority } from "@/lib/crm/types";
import { toast } from "sonner";
import { PrototypeBadge } from "./prototype-badge";
import { CompleteTaskButton } from "./complete-task-button";

export function CrmTasksPage() {
  const crm = useCrm();
  const [status, setStatus] = useState<"open" | "done" | "all">("open");
  const [source, setSource] = useState<"all" | "agent" | "manual">("all");
  const [creating, setCreating] = useState(false);

  const tasks = useMemo(() => crm.tasks.filter((task) => {
    if (status !== "all" && task.status !== status) return false;
    if (source !== "all" && task.source !== source) return false;
    return true;
  }), [crm.tasks, source, status]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {(["open", "done", "all"] as const).map((item) => (
            <button key={item} type="button" onClick={() => setStatus(item)} className={`rounded-lg px-3 py-2 text-sm capitalize ${status === item ? "bg-white/[0.08] text-white" : "text-slate-400"}`}>
              {item}
            </button>
          ))}
          {(["all", "agent", "manual"] as const).map((item) => (
            <button key={item} type="button" onClick={() => setSource(item)} className={`rounded-lg px-3 py-2 text-sm capitalize ${source === item ? "bg-white/[0.08] text-white" : "text-slate-400"}`}>
              {item === "all" ? "Any source" : item}
            </button>
          ))}
        </div>
        <Button type="button" onClick={() => setCreating(true)}>New task</Button>
      </div>

      {tasks.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/10 px-6 py-16 text-center text-sm text-slate-400">
          No tasks in this view.
        </div>
      ) : (
        <ul className="divide-y divide-white/[0.05] rounded-2xl border border-white/[0.06]">
          {tasks.map((task) => {
            const overdue = task.status === "open" && new Date(task.dueDate).getTime() < Date.now();
            return (
              <li key={task.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm text-white">{task.title}</p>
                    {task.source === "agent" && <PrototypeBadge label="Agent created" tone="default" />}
                    <span className="text-xs capitalize text-slate-500">{task.priority}</span>
                  </div>
                  <p className={`text-xs ${overdue ? "text-red-300" : "text-slate-400"}`}>
                    <Link href={`/crm/companies/${task.companyId}`} className="hover:underline">{crm.companyById(task.companyId)?.name}</Link>
                    {" · "}{task.owner} · due {formatDate(task.dueDate)}
                    {overdue ? " · overdue" : ""}
                  </p>
                  {task.suggestedAction && <p className="mt-1 text-xs text-indigo-200">{task.suggestedAction}</p>}
                </div>
                {task.status === "open" ? (
                  <CompleteTaskButton taskId={task.id} />
                ) : (
                  <span className="text-xs text-emerald-300">Done</span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <TaskDialog open={creating} onOpenChange={setCreating} />
    </div>
  );
}

function TaskDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const crm = useCrm();
  const [companyId, setCompanyId] = useState(crm.companies[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState<string>(OWNERS[0]);
  const [dueDate, setDueDate] = useState(new Date().toISOString().slice(0, 10));
  const [priority, setPriority] = useState<TaskPriority>("normal");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      toast.error("Add a task title.");
      return;
    }
    const opportunity = crm.opportunities.find((item) => item.companyId === companyId);
    crm.createTask({
      companyId,
      opportunityId: opportunity?.id ?? null,
      title: title.trim(),
      owner,
      dueDate: new Date(dueDate).toISOString(),
      priority,
      source: "manual",
    });
    toast.success("Task created.");
    setTitle("");
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#0c111c] text-slate-200">
        <DialogHeader>
          <DialogTitle>New task</DialogTitle>
          <DialogDescription>Manual task. Agent-created tasks come from suggestions.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="task-company">Company</Label>
            <select id="task-company" className="flex h-11 w-full rounded-md border border-input bg-background px-3 text-sm" value={companyId} onChange={(event) => setCompanyId(event.target.value)}>
              {crm.companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="task-title">Title</Label>
            <Input id="task-title" value={title} onChange={(event) => setTitle(event.target.value)} required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="task-owner">Owner</Label>
              <select id="task-owner" className="flex h-11 w-full rounded-md border border-input bg-background px-3 text-sm" value={owner} onChange={(event) => setOwner(event.target.value)}>
                {OWNERS.map((name) => <option key={name}>{name}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="task-due">Due</Label>
              <Input id="task-due" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="task-priority">Priority</Label>
            <select id="task-priority" className="flex h-11 w-full rounded-md border border-input bg-background px-3 text-sm" value={priority} onChange={(event) => setPriority(event.target.value as TaskPriority)}>
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
            </select>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit">Create task</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
