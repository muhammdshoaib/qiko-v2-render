"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { SEED } from "./seed";
import type { Activity, CrmState, Opportunity, PipelineStage, Task } from "./types";
import {
  applyClaudeEmailApprove,
  applyClaudeEmailDraft,
  applyClaudeEmailHold,
  applyClaudeStatus,
  applySlackRevenueFinance,
  applySlackRevenueSummary,
  applySlackSalesFinance,
  applySlackSalesOps,
} from "./channels";
import type { DemoUserId } from "./types";
import {
  WORKFLOW_IDS,
  applyInvoiceStart,
  applyMeetingApprove,
  applyMeetingStart,
  applyStalledOwnerComplete,
  applyStalledStart,
} from "./workflows";

const STORAGE_KEY = "qiko-crm-prototype-v3";

type CrmStore = CrmState & {
  ready: boolean;
  companyById: (id: string) => CrmState["companies"][number] | undefined;
  moveOpportunity: (id: string, stage: PipelineStage) => void;
  saveOpportunity: (input: Omit<Opportunity, "createdAt" | "lastActivityAt"> & { createdAt?: string }) => void;
  completeTask: (id: string, evidence?: string) => string | void;
  createTask: (input: Omit<Task, "id" | "status">) => void;
  addNote: (companyId: string, opportunityId: string | null, detail: string) => void;
  applySuggestion: (id: string) => string;
  runStalledWorkflow: () => string;
  completeStalledFollowUp: (evidence: string) => string;
  runMeetingWorkflow: () => string;
  approveMeetingStage: () => string;
  runInvoiceWorkflow: () => string;
  askClaudeStatus: () => string;
  askClaudeEmailDraft: () => string;
  holdClaudeEmail: () => string;
  approveClaudeEmail: () => string;
  askSlackSalesOps: (userId: DemoUserId) => string;
  askSlackSalesFinance: (userId: DemoUserId) => string;
  askSlackRevenueSummary: (userId: DemoUserId) => string;
  askSlackRevenueFinance: (userId: DemoUserId) => string;
  reset: () => void;
};

const CrmContext = createContext<CrmStore | null>(null);

function persist(state: CrmState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function markSuggestion(
  state: CrmState,
  action: CrmState["suggestions"][number]["action"],
  companyId: string,
  applied = true,
): CrmState {
  if (!applied) return state;
  return {
    ...state,
    suggestions: state.suggestions.map((item) =>
      item.action === action && item.companyId === companyId ? { ...item, applied: true } : item,
    ),
  };
}

function addActivity(state: CrmState, activity: Omit<Activity, "id" | "at">): CrmState {
  return {
    ...state,
    activities: [
      { ...activity, id: `a-${crypto.randomUUID().slice(0, 8)}`, at: new Date().toISOString() },
      ...state.activities,
    ],
  };
}

export function CrmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CrmState>(SEED);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as CrmState;
        const hydrated: CrmState = {
          ...SEED,
          ...parsed,
          opportunities: (parsed.opportunities ?? SEED.opportunities).map((opp) => {
            const seedOpp = SEED.opportunities.find((item) => item.id === opp.id);
            return { ...opp, estimatedCost: opp.estimatedCost ?? seedOpp?.estimatedCost };
          }),
          workflowEvents: parsed.workflowEvents ?? [],
          workflowRuns: parsed.workflowRuns?.length ? parsed.workflowRuns : SEED.workflowRuns,
          channelRuns: parsed.channelRuns?.length ? parsed.channelRuns : SEED.channelRuns,
          channelMessages: parsed.channelMessages ?? [],
          emailDraft: parsed.emailDraft ?? null,
        };
        const runStatus = (id: CrmState["workflowRuns"][number]["id"]) =>
          hydrated.workflowRuns.find((run) => run.id === id)?.status;
        setState(
          markSuggestion(
            markSuggestion(
              markSuggestion(
                hydrated,
                "follow_up",
                "albemarle",
                runStatus("stalled") !== "idle",
              ),
              "stage_review",
              "harrow",
              runStatus("meeting") !== "idle",
            ),
            "invoice_nudge",
            "lumen",
            runStatus("invoice") !== "idle",
          ),
        );
      }
    } catch {
      // Keep seed if stored JSON is unreadable.
    }
    setReady(true);
  }, []);

  const api = useMemo<CrmStore>(() => {
    const write = (next: CrmState) => {
      setState(next);
      persist(next);
    };

    return {
      ...state,
      ready,
      companyById: (id) => state.companies.find((company) => company.id === id),
      moveOpportunity: (id, stage) => {
        const current = state.opportunities.find((item) => item.id === id);
        if (!current || current.stage === stage) return;
        write(addActivity({
          ...state,
          opportunities: state.opportunities.map((item) =>
            item.id === id ? { ...item, stage, lastActivityAt: new Date().toISOString() } : item,
          ),
        }, {
          companyId: current.companyId,
          opportunityId: id,
          kind: "human",
          title: "Stage moved",
          detail: `Moved to ${stage.replaceAll("_", " ")}.`,
        }));
      },
      saveOpportunity: (input) => {
        const existing = state.opportunities.find((item) => item.id === input.id);
        const record: Opportunity = {
          ...input,
          createdAt: existing?.createdAt ?? input.createdAt ?? new Date().toISOString(),
          lastActivityAt: new Date().toISOString(),
        };
        write(addActivity({
          ...state,
          opportunities: existing
            ? state.opportunities.map((item) => (item.id === record.id ? record : item))
            : [record, ...state.opportunities],
        }, {
          companyId: record.companyId,
          opportunityId: record.id,
          kind: "human",
          title: existing ? "Opportunity updated" : "Opportunity created",
          detail: record.title,
        }));
      },
      completeTask: (id, evidence) => {
        const task = state.tasks.find((item) => item.id === id);
        if (!task || task.status === "done") return;
        if (id === WORKFLOW_IDS.stalledTask) {
          const result = applyStalledOwnerComplete(state, evidence ?? "");
          write(result.state);
          return result.message;
        }
        write(addActivity({
          ...state,
          tasks: state.tasks.map((item) => (item.id === id ? { ...item, status: "done" } : item)),
        }, {
          companyId: task.companyId,
          opportunityId: task.opportunityId,
          kind: "human",
          title: "Task completed",
          detail: task.title,
        }));
      },
      createTask: (input) => {
        const task: Task = { ...input, id: `t-${crypto.randomUUID().slice(0, 8)}`, status: "open" };
        write(addActivity({
          ...state,
          tasks: [task, ...state.tasks],
        }, {
          companyId: task.companyId,
          opportunityId: task.opportunityId,
          kind: task.source === "agent" ? "agent" : "human",
          title: "Task created",
          detail: task.title,
        }));
      },
      addNote: (companyId, opportunityId, detail) => {
        write(addActivity(state, {
          companyId,
          opportunityId,
          kind: "human",
          title: "Note",
          detail,
        }));
      },
      applySuggestion: (id) => {
        const suggestion = state.suggestions.find((item) => item.id === id);
        if (!suggestion || suggestion.applied) return "Already applied.";
        if (suggestion.action === "follow_up" && suggestion.companyId === "albemarle") {
          const result = applyStalledStart(state);
          write({
            ...result.state,
            suggestions: result.state.suggestions.map((item) => (item.id === id ? { ...item, applied: true } : item)),
          });
          return result.message;
        }
        if (suggestion.action === "stage_review" && suggestion.companyId === "harrow") {
          const result = applyMeetingStart(state);
          write({
            ...result.state,
            suggestions: result.state.suggestions.map((item) => (item.id === id ? { ...item, applied: true } : item)),
          });
          return result.message;
        }
        if (suggestion.action === "invoice_nudge" && suggestion.companyId === "lumen") {
          const result = applyInvoiceStart(state);
          write({
            ...result.state,
            suggestions: result.state.suggestions.map((item) => (item.id === id ? { ...item, applied: true } : item)),
          });
          return result.message;
        }
        let next = {
          ...state,
          suggestions: state.suggestions.map((item) => (item.id === id ? { ...item, applied: true } : item)),
        };
        next = addActivity(next, {
          companyId: suggestion.companyId,
          opportunityId: suggestion.opportunityId,
          kind: "agent",
          title: "Agent action applied (mock)",
          detail: suggestion.message,
        });
        write(next);
        return suggestion.action === "email_sent"
          ? "This was already recorded as a mock send."
          : "Updated locally. No live integration ran.";
      },
      runStalledWorkflow: () => {
        const result = applyStalledStart(state);
        write(markSuggestion(result.state, "follow_up", "albemarle"));
        return result.message;
      },
      completeStalledFollowUp: (evidence) => {
        const result = applyStalledOwnerComplete(state, evidence);
        write(markSuggestion(result.state, "follow_up", "albemarle"));
        return result.message;
      },
      runMeetingWorkflow: () => {
        const result = applyMeetingStart(state);
        write(markSuggestion(result.state, "stage_review", "harrow"));
        return result.message;
      },
      approveMeetingStage: () => {
        const result = applyMeetingApprove(state);
        write(markSuggestion(result.state, "stage_review", "harrow"));
        return result.message;
      },
      runInvoiceWorkflow: () => {
        const result = applyInvoiceStart(state);
        write(markSuggestion(result.state, "invoice_nudge", "lumen"));
        return result.message;
      },
      askClaudeStatus: () => {
        const result = applyClaudeStatus(state);
        write(result.state);
        return result.message;
      },
      askClaudeEmailDraft: () => {
        const result = applyClaudeEmailDraft(state);
        write(result.state);
        return result.message;
      },
      holdClaudeEmail: () => {
        const result = applyClaudeEmailHold(state);
        write(result.state);
        return result.message;
      },
      approveClaudeEmail: () => {
        const result = applyClaudeEmailApprove(state);
        write(result.state);
        return result.message;
      },
      askSlackSalesOps: (userId) => {
        const result = applySlackSalesOps(state, userId);
        write(result.state);
        return result.message;
      },
      askSlackSalesFinance: (userId) => {
        const result = applySlackSalesFinance(state, userId);
        write(result.state);
        return result.message;
      },
      askSlackRevenueSummary: (userId) => {
        const result = applySlackRevenueSummary(state, userId);
        write(result.state);
        return result.message;
      },
      askSlackRevenueFinance: (userId) => {
        const result = applySlackRevenueFinance(state, userId);
        write(result.state);
        return result.message;
      },
      reset: () => {
        write(SEED);
      },
    };
  }, [ready, state]);

  return <CrmContext.Provider value={api}>{children}</CrmContext.Provider>;
}

export function useCrm() {
  const value = useContext(CrmContext);
  if (!value) throw new Error("useCrm must be used inside CrmProvider");
  return value;
}
