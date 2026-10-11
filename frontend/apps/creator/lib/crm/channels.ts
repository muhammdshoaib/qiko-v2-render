import { formatDate, formatMoney, stageLabel } from "./format";
import {
  authorize,
  hasRestrictedValue,
  projectOpenPipeline,
  projectOpportunity,
  type AccessDecision,
} from "./policy";
import type {
  Activity,
  ChannelMessage,
  ChannelRun,
  ChannelScenarioId,
  CrmState,
  DemoUserId,
  WorkflowEvent,
} from "./types";

export const CHANNEL_IDS = {
  albemarleTask: "t-wf-stalled",
  albemarleOpp: "o-alb",
} as const;

export const EMPTY_CHANNEL_RUNS: ChannelRun[] = [
  { id: "claude-status", status: "idle", completedSteps: [] },
  { id: "claude-email", status: "idle", completedSteps: [] },
  { id: "slack-sales-ops", status: "idle", completedSteps: [] },
  { id: "slack-sales-finance", status: "idle", completedSteps: [] },
  { id: "slack-revenue-summary", status: "idle", completedSteps: [] },
  { id: "slack-revenue-finance", status: "idle", completedSteps: [] },
  { id: "slack-revenue-denied", status: "idle", completedSteps: [] },
];

const MEETING_NOTE = "Helena asked how Intent Monitor stays off the investor app. Tom wants a written boundary.";

const EMAIL_DRAFT = {
  to: "helena.ward@albemarle.example",
  toName: "Helena Ward",
  subject: "Intelligence layer pilot — next step and written boundary",
  body: `Helena,

Thank you for the working session with Tom. You asked how Intent Monitor stays off the investor app, and Tom asked for a written boundary.

I am sharing a one-page outline of the two workers and the hard walls, including that investor-facing surfaces do not receive intent scores.

If useful, we can walk through it this week.

Maya Chen`,
  approved: false,
};

function now() {
  return new Date().toISOString();
}

function hasEvent(state: CrmState, id: string) {
  return state.workflowEvents.some((item) => item.id === id);
}

function patchChannelRun(state: CrmState, id: ChannelScenarioId, patch: Partial<ChannelRun>): CrmState {
  return {
    ...state,
    channelRuns: state.channelRuns.map((run) => (run.id === id ? { ...run, ...patch } : run)),
  };
}

function pushEvent(state: CrmState, event: Omit<WorkflowEvent, "at">, activity?: Omit<Activity, "id" | "at">): CrmState {
  if (hasEvent(state, event.id)) return state;
  const at = now();
  return {
    ...state,
    workflowEvents: [{ ...event, at }, ...state.workflowEvents],
    activities: activity
      ? [{ ...activity, id: event.id, at }, ...state.activities]
      : state.activities,
  };
}

function pushMessages(
  state: CrmState,
  scenarioId: ChannelScenarioId,
  surface: ChannelMessage["surface"],
  userId: DemoUserId,
  userText: string,
  agentText: string,
  outcome: ChannelMessage["outcome"],
  key: string = scenarioId,
): CrmState {
  if (state.channelMessages.some((item) => item.id === `${key}-user`)) return state;
  const at = now();
  const user: ChannelMessage = {
    id: `${key}-user`,
    surface,
    userId,
    role: "user",
    text: userText,
    at,
    scenarioId,
    outcome,
  };
  const agent: ChannelMessage = {
    id: `${key}-agent`,
    surface,
    userId,
    role: "agent",
    text: agentText,
    at,
    scenarioId,
    outcome,
  };
  return { ...state, channelMessages: [...state.channelMessages, user, agent] };
}

function strippedFinanceKeys(projected: Record<string, unknown>) {
  return ["value", "expectedRevenue", "estimatedCost", "amount", "pipelineTotal"].filter((key) => !(key in projected));
}

function safeText(text: string, access: AccessDecision, fallback: string) {
  if (!access.financial && hasRestrictedValue(text)) return fallback;
  return text;
}

export function applyClaudeStatus(state: CrmState): { state: CrmState; message: string } {
  const access = authorize("maya", "claude");
  const projected = projectOpportunity(state, "albemarle", access);
  if (!projected) return { state, message: "Albemarle is not in the permitted record." };

  const question = "What's the current status of Albemarle, and what needs doing next?";
  const answer = [
    `${projected.companyName} is ${stageLabel(projected.stage)} on ${projected.title}.`,
    `Owner: ${projected.owner}.`,
    `Last recorded discussion: ${MEETING_NOTE}`,
    `Next action: ${projected.nextStep} (open task assigned to ${projected.owner}).`,
    "CRM record: /crm/companies/albemarle",
  ].join(" ");

  let next = pushMessages(state, "claude-status", "claude", "maya", question, answer, "allowed");
  next = pushEvent(next, {
    id: "ev-claude-status-read",
    workflowId: "claude-status",
    step: "read",
    title: "Claude retrieved Albemarle status",
    detail: "Permitted operational fields only for this question. Prototype retrieval — not a live Claude session.",
    filter: "allowed",
    edgeId: "agent-claude-read",
    focus: "claude",
    crmHref: "/crm/companies/albemarle",
  });
  next = patchChannelRun(next, "claude-status", { status: "complete", completedSteps: ["read"] });
  return { state: next, message: "Albemarle status retrieved in the Claude walkthrough." };
}

export function applyClaudeEmailDraft(state: CrmState): { state: CrmState; message: string } {
  const run = state.channelRuns.find((item) => item.id === "claude-email");
  if (run?.status === "complete") return { state, message: "The Albemarle follow-up is already approved in this prototype." };
  if (run?.status === "awaiting_approval" && state.emailDraft) {
    return { state, message: "A draft is already waiting for approval. It has not been sent." };
  }

  const question = "Prepare a follow-up email for Albemarle based on our last meeting.";
  const answer = `Draft prepared for ${EMAIL_DRAFT.toName}. It will not send, and it does not close the follow-up task, until you approve.`;

  let next: CrmState = { ...state, emailDraft: { ...EMAIL_DRAFT } };
  next = pushMessages(next, "claude-email", "claude", "maya", question, answer, "approval");
  next = pushEvent(next, {
    id: "ev-claude-email-draft",
    workflowId: "claude-email",
    step: "draft",
    title: "Follow-up email drafted",
    detail: "Draft for Helena Ward from the recorded working session. Not sent. Task still open.",
    filter: "approval",
    edgeId: "agent-email-review",
    focus: "email",
    crmHref: "/crm/companies/albemarle",
  });
  next = patchChannelRun(next, "claude-email", { status: "awaiting_approval", completedSteps: ["draft"] });
  return { state: next, message: "Draft ready for review. Prototype only — no mailbox is connected." };
}

export function applyClaudeEmailHold(state: CrmState): { state: CrmState; message: string } {
  if (!state.emailDraft || state.emailDraft.approved) {
    return { state, message: "There is no open draft to hold." };
  }
  let next = pushEvent(state, {
    id: "ev-claude-email-held",
    workflowId: "claude-email",
    step: "held",
    title: "Follow-up email held",
    detail: "Operator held the draft. Nothing was sent. The Albemarle task stays open.",
    filter: "allowed",
    edgeId: "agent-email-review",
    focus: "email",
    crmHref: "/crm/companies/albemarle",
  });
  next = {
    ...next,
    emailDraft: null,
    channelMessages: [
      ...next.channelMessages,
      {
        id: "claude-email-held",
        surface: "claude",
        userId: "maya",
        role: "system",
        text: "Held. The draft was not sent. The follow-up task remains open.",
        at: now(),
        scenarioId: "claude-email",
        outcome: "allowed",
      },
    ],
  };
  next = patchChannelRun(next, "claude-email", { status: "idle", completedSteps: ["draft", "held"] });
  return { state: next, message: "Draft held. Task still open. Prototype only." };
}

export function applyClaudeEmailApprove(state: CrmState): { state: CrmState; message: string } {
  if (!state.emailDraft) return { state, message: "Prepare the draft first." };
  if (state.emailDraft.approved) return { state, message: "This follow-up is already approved in the prototype." };

  const evidence = "Approved outbound to Helena Ward. Prototype — no mail was delivered.";
  let next: CrmState = {
    ...state,
    emailDraft: { ...state.emailDraft, approved: true },
    tasks: state.tasks.map((item) => (item.id === CHANNEL_IDS.albemarleTask ? { ...item, status: "done" } : item)),
    opportunities: state.opportunities.map((item) =>
      item.id === CHANNEL_IDS.albemarleOpp
        ? { ...item, lastActivityAt: now(), nextStep: "Wait for Helena's written response" }
        : item,
    ),
  };

  next = pushEvent(next, {
    id: "ev-claude-email-approved",
    workflowId: "claude-email",
    step: "approved",
    title: "Follow-up email approved",
    detail: "Human confirmed the draft. Connected send would run only if a mailbox is configured.",
    filter: "completed",
    edgeId: "agent-email-review",
    focus: "email",
    crmHref: "/crm/companies/albemarle",
  });
  next = pushEvent(next, {
    id: "ev-claude-email-sent",
    workflowId: "claude-email",
    step: "sent",
    title: "Email action recorded (prototype)",
    detail: "No mailbox is connected. Nothing was delivered.",
    filter: "completed",
    edgeId: "agent-email-review",
    focus: "email",
    crmHref: "/crm/companies/albemarle",
  });
  next = pushEvent(next, {
    id: "ev-claude-email-crm",
    workflowId: "claude-email",
    step: "record",
    title: "CRM updated after approved follow-up",
    detail: evidence,
    filter: "completed",
    edgeId: "agent-record",
    focus: "record",
    crmHref: "/crm/companies/albemarle",
  }, {
    companyId: "albemarle",
    opportunityId: CHANNEL_IDS.albemarleOpp,
    kind: "human",
    title: "Follow-up email approved",
    detail: evidence,
  });
  next = {
    ...next,
    channelMessages: [
      ...next.channelMessages,
      {
        id: "claude-email-approved",
        surface: "claude",
        userId: "maya",
        role: "system",
        text: "Approved. CRM task closed on that evidence. Prototype — no mail delivered.",
        at: now(),
        scenarioId: "claude-email",
        outcome: "completed",
      },
    ],
  };
  next = patchChannelRun(next, "claude-email", {
    status: "complete",
    completedSteps: ["draft", "approved", "sent", "record"],
  });
  next = {
    ...next,
    workflowRuns: next.workflowRuns.map((run) =>
      run.id === "stalled" && run.status !== "idle"
        ? { ...run, status: "complete" as const, completedSteps: [...new Set([...run.completedSteps, "email", "record"])] }
        : run,
    ),
  };
  return { state: next, message: "Approved. CRM updated. Prototype — no mail delivered." };
}

function slackFinanceDenial(access: AccessDecision) {
  if (access.deniedBy === "channel") {
    return "I cannot share deal value or estimated delivery cost in #sales-pipeline. Those fields were removed before this reply was written. Ask in #revenue if you are individually authorised.";
  }
  return "I cannot share financial figures. Your user grant does not include finance, even in #revenue. The values were not loaded into this reply.";
}

export function applySlackSalesOps(state: CrmState, userId: DemoUserId): { state: CrmState; message: string } {
  const access = authorize(userId, "slack-sales");
  const projected = projectOpportunity(state, "albemarle", access);
  if (!projected) return { state, message: "Albemarle is not in the permitted record." };

  const question = "What's happening with Albemarle and what are our next steps?";
  const answer = safeText([
    `${projected.companyName} is ${stageLabel(projected.stage)}.`,
    `Owner ${projected.owner}.`,
    `Recent discussion: ${MEETING_NOTE}`,
    `Next step: ${projected.nextStep}.`,
  ].join(" "), access, slackFinanceDenial(access));

  let next = pushMessages(state, "slack-sales-ops", "slack-sales", userId, question, answer, "allowed");
  next = pushEvent(next, {
    id: "ev-slack-sales-ops",
    workflowId: "slack-sales-ops",
    step: "ops",
    title: "Pipeline question answered in #sales-pipeline",
    detail: "Stage, owner, and next step only. Prototype — nothing was posted to Slack.",
    filter: "allowed",
    edgeId: "agent-slack-sales-read",
    focus: "slack-sales",
    crmHref: "/crm/companies/albemarle",
  });
  next = patchChannelRun(next, "slack-sales-ops", { status: "complete", completedSteps: ["ops"] });
  return { state: next, message: "Operational answer recorded for #sales-pipeline." };
}

export function applySlackSalesFinance(state: CrmState, userId: DemoUserId): { state: CrmState; message: string } {
  const access = authorize(userId, "slack-sales");
  const projected = projectOpportunity(state, "albemarle", access) ?? {};
  const question = "What's the Albemarle deal value and estimated delivery cost?";
  const answer = slackFinanceDenial(access);

  let next = pushMessages(state, "slack-sales-finance", "slack-sales", userId, question, answer, "blocked");
  next = pushEvent(next, {
    id: "ev-slack-sales-blocked",
    workflowId: "slack-sales-finance",
    step: "blocked",
    title: "Financial question blocked in #sales-pipeline",
    detail: `${access.reason ?? "Channel wall."} Fields removed: ${strippedFinanceKeys(projected as Record<string, unknown>).join(", ") || "value, estimatedCost"}. No figures in this event.`,
    filter: "blocked",
    edgeId: "agent-slack-sales-blocked",
    focus: "slack-sales",
    crmHref: "/crm/companies/albemarle",
  });
  next = patchChannelRun(next, "slack-sales-finance", { status: "blocked", completedSteps: ["blocked"] });
  return { state: next, message: "Channel wall applied. No values disclosed." };
}

export function applySlackRevenueSummary(state: CrmState, userId: DemoUserId): { state: CrmState; message: string } {
  const access = authorize(userId, "slack-revenue");
  const projected = projectOpenPipeline(state, access);
  const question = "Which customers have upcoming invoices and what is the total open pipeline value?";

  if (!access.financial) {
    const answer = slackFinanceDenial(access);
    let next = pushMessages(state, "slack-revenue-denied", "slack-revenue", userId, question, answer, "blocked", "slack-revenue-denied-summary");
    next = pushEvent(next, {
      id: "ev-slack-revenue-denied-summary",
      workflowId: "slack-revenue-denied",
      step: "denied",
      title: "Revenue summary denied",
      detail: `${access.reason} No invoice amounts or pipeline totals included.`,
      filter: "blocked",
      edgeId: "agent-slack-revenue",
      focus: "slack-revenue",
      crmHref: "/crm/invoices",
    });
    next = patchChannelRun(next, "slack-revenue-denied", { status: "blocked", completedSteps: ["denied"] });
    return { state: next, message: "User wall applied in #revenue." };
  }

  const lines = projected.invoices.map((item) =>
    `${item.companyName} ${item.number} · ${item.status} · ${formatDate(item.dueDate)}${item.amount != null ? ` · ${formatMoney(item.amount)}` : ""}`,
  );
  const answer = `Open invoices: ${lines.join("; ")}. Open pipeline value: ${formatMoney(projected.pipelineTotal ?? 0)} across ${projected.count} opportunities.`;
  let next = pushMessages(state, "slack-revenue-summary", "slack-revenue", userId, question, answer, "allowed");
  next = pushEvent(next, {
    id: "ev-slack-revenue-summary",
    workflowId: "slack-revenue-summary",
    step: "summary",
    title: "Revenue summary returned",
    detail: "Authorised #revenue summary from the same CRM store. Prototype — nothing was posted to Slack.",
    filter: "allowed",
    edgeId: "agent-slack-revenue",
    focus: "slack-revenue",
    crmHref: "/crm/invoices",
  });
  next = patchChannelRun(next, "slack-revenue-summary", { status: "complete", completedSteps: ["summary"] });
  return { state: next, message: "Authorised revenue summary recorded." };
}

export function applySlackRevenueFinance(state: CrmState, userId: DemoUserId): { state: CrmState; message: string } {
  const access = authorize(userId, "slack-revenue");
  const projected = projectOpportunity(state, "albemarle", access);
  const question = "What's the Albemarle deal value and estimated delivery cost?";

  if (!access.financial || !projected) {
    const denied = slackFinanceDenial(access);
    let next = pushMessages(state, "slack-revenue-denied", "slack-revenue", userId, question, denied, "blocked", "slack-revenue-denied-finance");
    next = pushEvent(next, {
      id: "ev-slack-revenue-denied-finance",
      workflowId: "slack-revenue-denied",
      step: "denied",
      title: "Albemarle values denied in #revenue",
      detail: `${access.reason} No deal value or cost included.`,
      filter: "blocked",
      edgeId: "agent-slack-revenue",
      focus: "slack-revenue",
      crmHref: "/crm/companies/albemarle",
    });
    next = patchChannelRun(next, "slack-revenue-denied", { status: "blocked", completedSteps: ["denied"] });
    return { state: next, message: "User wall applied in #revenue." };
  }

  const answer = `${projected.companyName} deal value ${formatMoney(projected.value ?? 0)}. Estimated delivery cost ${projected.estimatedCost != null ? formatMoney(projected.estimatedCost) : "not on file"}.`;
  let next = pushMessages(state, "slack-revenue-finance", "slack-revenue", userId, question, answer, "allowed");
  next = pushEvent(next, {
    id: "ev-slack-revenue-finance",
    workflowId: "slack-revenue-finance",
    step: "finance",
    title: "Albemarle values returned in #revenue",
    detail: "Authorised user received projected financial fields. Prototype — nothing was posted to Slack.",
    filter: "allowed",
    edgeId: "agent-slack-revenue",
    focus: "slack-revenue",
    crmHref: "/crm/companies/albemarle",
  });
  next = patchChannelRun(next, "slack-revenue-finance", { status: "complete", completedSteps: ["finance"] });
  return { state: next, message: "Authorised Albemarle values recorded." };
}

export function channelRunLabel(id: ChannelScenarioId) {
  if (id === "claude-status") return "Claude · Albemarle status";
  if (id === "claude-email") return "Claude · follow-up email";
  if (id === "slack-sales-ops") return "#sales-pipeline · ops";
  if (id === "slack-sales-finance") return "#sales-pipeline · finance wall";
  if (id === "slack-revenue-summary") return "#revenue · invoices";
  if (id === "slack-revenue-finance") return "#revenue · Albemarle values";
  return "#revenue · unauthorised";
}
