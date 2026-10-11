import type { Activity, CrmState, Task, WorkflowEvent, WorkflowRun } from "./types";

export const WORKFLOW_IDS = {
  stalledTask: "t-wf-stalled",
  meetingTerms: "t-wf-meeting-terms",
  meetingKickoff: "t-wf-meeting-kickoff",
  invoiceTask: "t-wf-invoice-lumen",
  stalledOpp: "o-alb",
  meetingOpp: "o-hs",
  invoiceId: "i3",
} as const;

export const EMPTY_RUNS: WorkflowRun[] = [
  { id: "stalled", status: "idle", completedSteps: [], pendingApproval: null },
  { id: "meeting", status: "idle", completedSteps: [], pendingApproval: null },
  { id: "invoice", status: "idle", completedSteps: [], pendingApproval: null },
];

function now() {
  return new Date().toISOString();
}

function hasEvent(state: CrmState, id: string) {
  return state.workflowEvents.some((item) => item.id === id);
}

function hasTask(state: CrmState, id: string) {
  return state.tasks.some((item) => item.id === id);
}

function patchRun(state: CrmState, id: WorkflowRun["id"], patch: Partial<WorkflowRun>): CrmState {
  return {
    ...state,
    workflowRuns: state.workflowRuns.map((run) => (run.id === id ? { ...run, ...patch } : run)),
  };
}

function pushEvent(state: CrmState, event: Omit<WorkflowEvent, "at">, activity: Omit<Activity, "id" | "at">): CrmState {
  if (hasEvent(state, event.id)) return state;
  const at = now();
  return {
    ...state,
    workflowEvents: [{ ...event, at }, ...state.workflowEvents],
    activities: [{ ...activity, id: event.id, at }, ...state.activities],
  };
}

function addTask(state: CrmState, task: Task): CrmState {
  if (hasTask(state, task.id)) return state;
  return { ...state, tasks: [task, ...state.tasks] };
}

export function applyStalledStart(state: CrmState): { state: CrmState; message: string } {
  const run = state.workflowRuns.find((item) => item.id === "stalled");
  if (run?.status === "complete") return { state, message: "Albemarle follow-up is already complete in this prototype." };
  if (run?.status === "awaiting_owner") return { state, message: "The Albemarle follow-up task already exists. Close it from Claude or with recorded evidence." };

  const opp = state.opportunities.find((item) => item.id === WORKFLOW_IDS.stalledOpp);
  if (!opp) return { state, message: "Albemarle opportunity is missing from the sample set." };

  let next = state;
  next = pushEvent(next, {
    id: "ev-stalled-detect",
    workflowId: "stalled",
    step: "detect",
    title: "Inactive opportunity identified",
    detail: "Albemarle had no meaningful activity for 8 days.",
    filter: "allowed",
    edgeId: "agent-crm-read",
    focus: "crm",
    crmHref: "/crm/companies/albemarle",
  }, {
    companyId: "albemarle",
    opportunityId: opp.id,
    kind: "agent",
    title: "Stall detected (prototype)",
    detail: "No meaningful activity for 8 days. Drafts do not count as activity.",
  });

  next = addTask(next, {
    id: WORKFLOW_IDS.stalledTask,
    companyId: "albemarle",
    opportunityId: opp.id,
    title: "Send draft proposal to Helena Ward",
    owner: opp.owner,
    dueDate: now(),
    priority: "high",
    status: "open",
    source: "agent",
    suggestedAction: "Prepare the written boundary Helena and Tom asked for. A draft does not close this task.",
  });

  next = pushEvent(next, {
    id: "ev-stalled-task",
    workflowId: "stalled",
    step: "task",
    title: "Follow-up task created",
    detail: "Task assigned to Maya Chen on Albemarle.",
    filter: "completed",
    edgeId: "agent-crm-write",
    focus: "crm",
    crmHref: "/crm/tasks",
  }, {
    companyId: "albemarle",
    opportunityId: opp.id,
    kind: "agent",
    title: "Follow-up task created (prototype)",
    detail: "Send draft proposal to Helena Ward.",
  });

  next = pushEvent(next, {
    id: "ev-stalled-slack",
    workflowId: "stalled",
    step: "slack",
    title: "Owner notified in #sales-pipeline",
    detail: "Ops reminder only. No values posted. Prototype — nothing was posted to Slack.",
    filter: "allowed",
    edgeId: "agent-slack-sales-read",
    focus: "slack-sales",
    crmHref: "/crm/companies/albemarle",
  }, {
    companyId: "albemarle",
    opportunityId: opp.id,
    kind: "agent",
    title: "Slack notice prepared (prototype)",
    detail: "Maya Chen notified in #sales-pipeline. No financial values.",
  });

  next = patchRun(next, "stalled", {
    status: "awaiting_owner",
    completedSteps: ["detect", "task", "slack"],
  });
  return { state: next, message: "Albemarle follow-up created. The task stays open until an approved email or recorded outcome." };
}

export function applyStalledOwnerComplete(state: CrmState, evidence: string): { state: CrmState; message: string } {
  const trimmed = evidence.trim();
  if (!trimmed) return { state, message: "Record what happened before closing the task." };

  const task = state.tasks.find((item) => item.id === WORKFLOW_IDS.stalledTask);
  if (!task) return { state, message: "Run the stall playbook first." };
  if (task.status === "done") return { state, message: "This follow-up is already closed." };

  let next: CrmState = {
    ...state,
    tasks: state.tasks.map((item) => (item.id === task.id ? { ...item, status: "done" } : item)),
    opportunities: state.opportunities.map((item) =>
      item.id === WORKFLOW_IDS.stalledOpp
        ? { ...item, lastActivityAt: now(), nextStep: "Wait for Helena's written response" }
        : item,
    ),
  };

  next = pushEvent(next, {
    id: "ev-stalled-owner",
    workflowId: "stalled",
    step: "owner",
    title: "Owner completed follow-up",
    detail: trimmed,
    filter: "completed",
    edgeId: "agent-crm-write",
    focus: "crm",
    crmHref: "/crm/companies/albemarle",
  }, {
    companyId: "albemarle",
    opportunityId: WORKFLOW_IDS.stalledOpp,
    kind: "human",
    title: "Follow-up completed",
    detail: trimmed,
  });

  next = pushEvent(next, {
    id: "ev-stalled-record",
    workflowId: "stalled",
    step: "record",
    title: "CRM updated after verified follow-up",
    detail: "Albemarle last activity refreshed. Captured into the Qiko record.",
    filter: "completed",
    edgeId: "agent-record",
    focus: "record",
    crmHref: "/crm/companies/albemarle",
  }, {
    companyId: "albemarle",
    opportunityId: WORKFLOW_IDS.stalledOpp,
    kind: "system",
    title: "Record updated (prototype)",
    detail: "Stall cleared because the owner recorded an outcome — not because a draft existed.",
  });

  next = patchRun(next, "stalled", {
    status: "complete",
    completedSteps: ["detect", "task", "slack", "owner", "record"],
  });
  return { state: next, message: "Follow-up closed with evidence. CRM last activity updated. Prototype only." };
}

export function applyMeetingStart(state: CrmState): { state: CrmState; message: string } {
  const run = state.workflowRuns.find((item) => item.id === "meeting");
  if (run?.status === "complete") return { state, message: "Harrow meeting playbook is already complete." };
  if (run?.status === "awaiting_approval") return { state, message: "Tasks exist. Approve the stage change to finish." };

  const opp = state.opportunities.find((item) => item.id === WORKFLOW_IDS.meetingOpp);
  if (!opp) return { state, message: "Harrow opportunity is missing from the sample set." };

  const note = "Callum said the proposal is directionally accepted, pending payment terms.";
  let next = pushEvent(state, {
    id: "ev-meeting-notes",
    workflowId: "meeting",
    step: "notes",
    title: "Meeting outcome recorded",
    detail: note,
    filter: "allowed",
    edgeId: "agent-crm-read",
    focus: "crm",
    crmHref: "/crm/companies/harrow",
  }, {
    companyId: "harrow",
    opportunityId: opp.id,
    kind: "human",
    title: "Meeting outcome",
    detail: note,
  });

  next = addTask(next, {
    id: WORKFLOW_IDS.meetingTerms,
    companyId: "harrow",
    opportunityId: opp.id,
    title: "Send written payment terms to Callum Reid",
    owner: opp.owner,
    dueDate: now(),
    priority: "high",
    status: "open",
    source: "agent",
    suggestedAction: "Extracted from the recorded note: pending payment terms.",
  });
  next = addTask(next, {
    id: WORKFLOW_IDS.meetingKickoff,
    companyId: "harrow",
    opportunityId: opp.id,
    title: "Hold confirmation until terms are accepted",
    owner: opp.owner,
    dueDate: now(),
    priority: "normal",
    status: "open",
    source: "agent",
    suggestedAction: "The note accepts the proposal directionally. It does not invent a kickoff date.",
  });

  next = pushEvent(next, {
    id: "ev-meeting-tasks",
    workflowId: "meeting",
    step: "tasks",
    title: "Meeting tasks created",
    detail: "Two tasks linked to Harrow Street — only commitments present in the note.",
    filter: "completed",
    edgeId: "agent-crm-write",
    focus: "crm",
    crmHref: "/crm/tasks",
  }, {
    companyId: "harrow",
    opportunityId: opp.id,
    kind: "agent",
    title: "Tasks created from meeting note (prototype)",
    detail: "Payment terms + hold confirmation. No invented commitments.",
  });

  next = pushEvent(next, {
    id: "ev-meeting-proposed",
    workflowId: "meeting",
    step: "proposed",
    title: "Stage update proposed",
    detail: "Harrow Street · Negotiation → Confirmed. Awaiting sign-off.",
    filter: "approval",
    edgeId: "agent-claude-review",
    focus: "claude",
    crmHref: "/crm/pipeline",
  }, {
    companyId: "harrow",
    opportunityId: opp.id,
    kind: "agent",
    title: "Stage change proposed (prototype)",
    detail: "Evidence: directional acceptance in the recorded note. Not applied.",
  });

  next = patchRun(next, "meeting", {
    status: "awaiting_approval",
    completedSteps: ["notes", "tasks", "proposed"],
    pendingApproval: {
      opportunityId: opp.id,
      from: opp.stage,
      to: "confirmed",
      reason: "Recorded note: proposal directionally accepted, pending payment terms.",
    },
  });
  return { state: next, message: "Meeting playbook ran in the prototype. Stage change is waiting for approval." };
}

export function applyMeetingApprove(state: CrmState): { state: CrmState; message: string } {
  const run = state.workflowRuns.find((item) => item.id === "meeting");
  if (!run?.pendingApproval) return { state, message: "No Harrow stage proposal is waiting." };

  const { opportunityId, from, to } = run.pendingApproval;
  let next: CrmState = {
    ...state,
    opportunities: state.opportunities.map((item) =>
      item.id === opportunityId ? { ...item, stage: to, lastActivityAt: now(), nextStep: "Agree payment terms" } : item,
    ),
  };

  next = pushEvent(next, {
    id: "ev-meeting-approved",
    workflowId: "meeting",
    step: "approved",
    title: "Stage update approved",
    detail: `Human approved ${from.replaceAll("_", " ")} → ${to.replaceAll("_", " ")}.`,
    filter: "completed",
    edgeId: "agent-claude-review",
    focus: "claude",
    crmHref: "/crm/pipeline",
  }, {
    companyId: "harrow",
    opportunityId,
    kind: "human",
    title: "Stage change approved",
    detail: "Owner accepted the proposed move to Confirmed.",
  });

  next = pushEvent(next, {
    id: "ev-meeting-updated",
    workflowId: "meeting",
    step: "updated",
    title: "Pipeline stage updated",
    detail: "Harrow Street is Confirmed. Captured into the Qiko record.",
    filter: "completed",
    edgeId: "agent-record",
    focus: "record",
    crmHref: "/crm/pipeline",
  }, {
    companyId: "harrow",
    opportunityId,
    kind: "system",
    title: "Stage moved to Confirmed (prototype)",
    detail: "Applied after human approval. Not an automatic jump.",
  });

  next = patchRun(next, "meeting", {
    status: "complete",
    completedSteps: ["notes", "tasks", "proposed", "approved", "updated"],
    pendingApproval: null,
  });
  return { state: next, message: "Stage moved to Confirmed after approval. Prototype only." };
}

export function applyInvoiceStart(state: CrmState): { state: CrmState; message: string } {
  const run = state.workflowRuns.find((item) => item.id === "invoice");
  if (run?.status === "complete") return { state, message: "Invoice playbook already created the collection task." };

  const invoice = state.invoices.find((item) => item.id === WORKFLOW_IDS.invoiceId);
  if (!invoice) return { state, message: "Lumen invoice QIK-1101 is missing from the sample set." };

  let next = pushEvent(state, {
    id: "ev-invoice-due",
    workflowId: "invoice",
    step: "due",
    title: "Invoice due soon",
    detail: "QIK-1101 · £18,000 · due shortly. Status remains unpaid.",
    filter: "allowed",
    edgeId: "agent-crm-read",
    focus: "crm",
    crmHref: "/crm/invoices",
  }, {
    companyId: "lumen",
    opportunityId: invoice.opportunityId,
    kind: "agent",
    title: "Invoice monitor (prototype)",
    detail: "QIK-1101 is due soon. Not marked paid.",
  });

  next = pushEvent(next, {
    id: "ev-invoice-revenue",
    workflowId: "invoice",
    step: "revenue",
    title: "Revenue alert posted",
    detail: "Authorised #revenue alert: QIK-1101 · £18,000 · owner Maya Chen. Prototype — nothing was sent to Slack.",
    filter: "allowed",
    edgeId: "agent-slack-revenue",
    focus: "slack-revenue",
    crmHref: "/crm/invoices",
  }, {
    companyId: "lumen",
    opportunityId: invoice.opportunityId,
    kind: "agent",
    title: "#revenue alert prepared (prototype)",
    detail: "Amount and due date shown only on an authorised finance surface.",
  });

  next = addTask(next, {
    id: WORKFLOW_IDS.invoiceTask,
    companyId: "lumen",
    opportunityId: invoice.opportunityId,
    title: "Collection follow-up for QIK-1101",
    owner: "Maya Chen",
    dueDate: now(),
    priority: "high",
    status: "open",
    source: "agent",
    suggestedAction: "Chase the unpaid invoice. Do not mark it paid from this task.",
  });

  next = pushEvent(next, {
    id: "ev-invoice-task",
    workflowId: "invoice",
    step: "task",
    title: "Collection follow-up created",
    detail: "Task assigned to Maya Chen. Invoice QIK-1101 stays unpaid.",
    filter: "completed",
    edgeId: "agent-crm-write",
    focus: "crm",
    crmHref: "/crm/tasks",
  }, {
    companyId: "lumen",
    opportunityId: invoice.opportunityId,
    kind: "agent",
    title: "Collection task created (prototype)",
    detail: "Ownership is clear. Payment status is unchanged.",
  });

  next = patchRun(next, "invoice", {
    status: "complete",
    completedSteps: ["due", "revenue", "task"],
  });
  return { state: next, message: "Invoice playbook ran in the prototype: #revenue alert and collection task. Invoice not marked paid." };
}

export function runLabel(id: WorkflowRun["id"]) {
  if (id === "stalled") return "Stalled opportunity";
  if (id === "meeting") return "Meeting outcome";
  return "Invoice due";
}
