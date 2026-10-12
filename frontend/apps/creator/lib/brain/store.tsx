"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { ActivityFilter, ActivityItem, FocusId, WorkerId } from "@/components/intelligence-layer/model";

const STORAGE_KEY = "qiko-brain-demo-v1";

export type DemoUserId = "maya" | "owen";
export type SurfaceId = "claude" | "ops" | "leadership";

export type BrainMessage = {
  id: string;
  surface: SurfaceId;
  role: "user" | "worker";
  text: string;
  at: string;
};

export type BrainEvent = ActivityItem & { source: "studio" | "claude" | "slack" };

export type ChannelConfig = {
  opsName: string;
  leadershipName: string;
  opsAllowsSensitive: boolean;
  leadershipAllowsSensitive: boolean;
};

export type ApprovalStatus = "awaiting" | "approved" | "held";

export const USERS: Record<DemoUserId, { id: DemoUserId; name: string; role: string; sensitive: boolean }> = {
  maya: { id: "maya", name: "Maya Chen", role: "Operator", sensitive: true },
  owen: { id: "owen", name: "Owen Blake", role: "Analyst", sensitive: false },
};

export const SENSITIVE_QUESTION = "How concentrated is this client's London portfolio?";
export const SENSITIVE_ANSWER = "Labelled sample: this client has 3 holdings in London. Property Insights wrote that as a concentration card. It cannot contact them or tell them to buy or sell.";
export const OPS_QUESTION = "What's the next step on Lombe House?";
export const OPS_ANSWER = "The Intelligence Worker flagged repeat views. A leadership review is recommended. No investor was contacted.";

const DEFAULT_CONFIG: ChannelConfig = {
  opsName: "ops",
  leadershipName: "leadership",
  opsAllowsSensitive: false,
  leadershipAllowsSensitive: true,
};

export type AccessDecision = {
  sensitive: boolean;
  deniedBy: "channel" | "user" | null;
  reason: string | null;
};

export function authorize(userId: DemoUserId, surface: SurfaceId, config: ChannelConfig): AccessDecision {
  const user = USERS[userId];
  const allows = surface === "claude" ? true : surface === "ops" ? config.opsAllowsSensitive : config.leadershipAllowsSensitive;
  const label = surface === "claude" ? "Claude" : surface === "ops" ? `#${config.opsName}` : `#${config.leadershipName}`;
  if (allows && user.sensitive) return { sensitive: true, deniedBy: null, reason: null };
  if (!allows) {
    return { sensitive: false, deniedBy: "channel", reason: `Sensitive commercial figures are not permitted in ${label}.` };
  }
  return { sensitive: false, deniedBy: "user", reason: `${user.name} is not authorised for sensitive figures, even in ${label}.` };
}

export function channelLabel(surface: SurfaceId, config: ChannelConfig) {
  if (surface === "claude") return "Claude";
  if (surface === "ops") return `#${config.opsName}`;
  return `#${config.leadershipName}`;
}

type BrainState = {
  events: BrainEvent[];
  messages: BrainMessage[];
  approval: ApprovalStatus;
  config: ChannelConfig;
};

const SEED: BrainState = {
  events: [],
  messages: [],
  approval: "awaiting",
  config: DEFAULT_CONFIG,
};

type BrainApi = BrainState & {
  ready: boolean;
  askClaudeInsight: () => string;
  askClaudeFollowUp: () => string;
  approveFollowUp: () => string;
  holdFollowUp: () => string;
  askSlack: (surface: "ops" | "leadership", userId: DemoUserId, kind: "ops" | "sensitive") => string;
  updateConfig: (patch: Partial<ChannelConfig>) => void;
  resetDemo: () => void;
};

const BrainContext = createContext<BrainApi | null>(null);

function now() {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function event(partial: Omit<BrainEvent, "id"> & { id?: string }): BrainEvent {
  return {
    id: partial.id ?? `ev-${crypto.randomUUID().slice(0, 8)}`,
    title: partial.title,
    detail: partial.detail,
    at: partial.at,
    filter: partial.filter,
    edgeId: partial.edgeId,
    focus: partial.focus,
    source: partial.source,
  };
}

function loadState(): BrainState {
  if (typeof window === "undefined") return SEED;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return SEED;
    const parsed = JSON.parse(raw) as Partial<BrainState>;
    return {
      events: Array.isArray(parsed.events) ? parsed.events : [],
      messages: Array.isArray(parsed.messages) ? parsed.messages : [],
      approval: parsed.approval === "approved" || parsed.approval === "held" ? parsed.approval : "awaiting",
      config: { ...DEFAULT_CONFIG, ...parsed.config },
    };
  } catch {
    return SEED;
  }
}

function persist(next: BrainState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function BrainProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BrainState>(SEED);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setState(loadState());
    setReady(true);
  }, []);

  const api = useMemo<BrainApi>(() => {
    const commit = (updater: (prev: BrainState) => BrainState) => {
      setState((prev) => persist(updater(prev)));
    };

    return {
      ...state,
      ready,
      askClaudeInsight: () => {
        const at = now();
        commit((prev) => ({
          ...prev,
          messages: [...prev.messages, {
            id: `m-${crypto.randomUUID().slice(0, 6)}`, surface: "claude", role: "user",
            text: "What is Property Insights seeing on the portfolio?", at,
          }, {
            id: `m-${crypto.randomUUID().slice(0, 6)}`, surface: "claude", role: "worker",
            text: "I read each advised investor’s holdings and wrote grounded cards into their app. 3,104 of 4,180 received at least one insight this month. 412 got a concentration card. I did not contact anyone or advise a trade.", at,
          }],
          events: [event({
            title: "Claude retrieved a property insight",
            detail: "Grounded in per-investor portfolio checks. Illustrative — not a live Claude session.",
            at, filter: "allowed", edgeId: "property-chat", focus: "property-insights", source: "claude",
          }), ...prev.events],
        }));
        return "Property Insights answered from its existing knowledge.";
      },
      askClaudeFollowUp: () => {
        let already = false;
        commit((prev) => {
          if (prev.approval !== "awaiting") {
            already = true;
            return prev;
          }
          const at = now();
          return {
            ...prev,
            messages: [...prev.messages, {
              id: `m-${crypto.randomUUID().slice(0, 6)}`, surface: "claude", role: "user",
              text: "Recommend a follow-up for the Lombe House cluster.", at,
            }, {
              id: `m-${crypto.randomUUID().slice(0, 6)}`, surface: "claude", role: "worker",
              text: "Recommend a leadership review of repeat views on Lombe House / Derby. No investor email will be sent. Approve to write this to company intelligence.", at,
            }],
            events: [event({
              title: "Follow-up recommended",
              detail: "Intelligence Worker asked for a human review. Awaiting approval.",
              at, filter: "approval", edgeId: "intent-record", focus: "intent-intelligence", source: "claude",
            }), ...prev.events],
          };
        });
        return already ? "That follow-up has already been reviewed." : "A recommended review is waiting for approval.";
      },
      approveFollowUp: () => {
        let empty = false;
        commit((prev) => {
          if (prev.approval !== "awaiting") {
            empty = true;
            return prev;
          }
          const at = now();
          return {
            ...prev,
            approval: "approved",
            events: [event({
              title: "Lombe House review approved",
              detail: "The cluster is on the company record. No outbound contact was sent.",
              at, filter: "completed", edgeId: "intent-record", focus: "intent-intelligence", source: "studio",
            }), ...prev.events],
          };
        });
        return empty ? "Nothing is waiting for approval." : "Review recorded. The decision is on the company record.";
      },
      holdFollowUp: () => {
        let empty = false;
        commit((prev) => {
          if (prev.approval !== "awaiting") {
            empty = true;
            return prev;
          }
          const at = now();
          return {
            ...prev,
            approval: "held",
            events: [event({
              title: "Lombe House review held",
              detail: "No write to the company record. No investor was contacted.",
              at, filter: "allowed", edgeId: "intent-record", focus: "intent-intelligence", source: "studio",
            }), ...prev.events],
          };
        });
        return empty ? "Nothing is waiting for approval." : "Held. The recommendation stays open and nothing was written.";
      },
      askSlack: (surface, userId, kind) => {
        let result = "";
        commit((prev) => {
          const access = authorize(userId, surface, prev.config);
          const at = now();
          const user = USERS[userId];
          const label = channelLabel(surface, prev.config);
          const asked = kind === "sensitive" ? SENSITIVE_QUESTION : OPS_QUESTION;
          if (kind === "sensitive" && !access.sensitive) {
            const blocked = access.deniedBy === "user"
              ? `${user.name} is not authorised for client portfolio figures, even in ${label}.`
              : `${label} may share operational updates only. Client portfolio figures stay out of this channel.`;
            result = blocked;
            return {
              ...prev,
              messages: [...prev.messages, {
                id: `m-${crypto.randomUUID().slice(0, 6)}`, surface, role: "user", text: `${user.name}: ${asked}`, at,
              }, {
                id: `m-${crypto.randomUUID().slice(0, 6)}`, surface, role: "worker", text: blocked, at,
              }],
              events: [event({
                title: `Blocked in ${label}`,
                detail: blocked,
                at, filter: "blocked", edgeId: "property-chat", focus: "property-insights", source: "slack",
              }), ...prev.events],
            };
          }
          const answer = kind === "sensitive" ? SENSITIVE_ANSWER : OPS_ANSWER;
          result = answer;
          return {
            ...prev,
            messages: [...prev.messages, {
              id: `m-${crypto.randomUUID().slice(0, 6)}`, surface, role: "user", text: `${user.name}: ${asked}`, at,
            }, {
              id: `m-${crypto.randomUUID().slice(0, 6)}`, surface, role: "worker", text: answer, at,
            }],
            events: [event({
              title: kind === "sensitive" ? `Portfolio figure shared in ${label}` : `Operational update in ${label}`,
              detail: answer,
              at, filter: "allowed", edgeId: kind === "sensitive" ? "property-chat" : "intent-chat", focus: kind === "sensitive" ? "property-insights" : "intent-intelligence", source: "slack",
            }), ...prev.events],
          };
        });
        return result;
      },
      updateConfig: (patch) => commit((prev) => ({ ...prev, config: { ...prev.config, ...patch } })),
      resetDemo: () => commit(() => SEED),
    };
  }, [state]);

  return <BrainContext.Provider value={api}>{children}</BrainContext.Provider>;
}

export function useBrain() {
  const value = useContext(BrainContext);
  if (!value) throw new Error("useBrain must be used inside BrainProvider");
  return value;
}

export function studioAttention(approval: ApprovalStatus): { title: string; detail: string; at: string; status: "attention" | "completed"; origin: FocusId; originLabel: string; href: string }[] {
  if (approval === "awaiting") {
    return [{
      title: "Lombe House intent captured",
      detail: "Lombe House / Derby attracted repeated investor views. The Intelligence Worker flagged interest — no outreach was sent.",
      at: "Today, 09:40",
      status: "attention",
      origin: "intent-intelligence",
      originLabel: "Intelligence Worker",
      href: "/studio/w/intent-intelligence",
    }];
  }
  if (approval === "approved") {
    return [{
      title: "Lombe House review recorded",
      detail: "Leadership review is on the company record. No investor email was sent.",
      at: "Just now",
      status: "completed",
      origin: "record",
      originLabel: "Company intelligence",
      href: "/studio/intelligence?block=investors",
    }];
  }
  return [{
    title: "Lombe House review held",
    detail: "The recommendation is on hold. Nothing was written or sent.",
    at: "Just now",
    status: "completed",
    origin: "intent-intelligence",
    originLabel: "Intelligence Worker",
    href: "/studio/w/intent-intelligence",
  }];
}

export function extraCompleted(events: BrainEvent[]) {
  return events.filter((item) => item.filter === "completed").length;
}

export type { WorkerId, FocusId, ActivityFilter };
