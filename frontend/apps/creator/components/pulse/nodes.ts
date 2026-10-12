import {
  SYSTEMS,
  WORKERS,
  isWorkerId,
  type FocusId,
  type SystemId,
  type WorkerId,
} from "@/components/intelligence-layer/model";

export type PulseKind = "record" | "block" | "worker" | "source";

export type PulseNode = {
  id: FocusId;
  kind: PulseKind;
  name: string;
  kicker: string;
  summary: string;
  connects: string[];
};

export const PULSE_BLOCKS: SystemId[] = ["investor-app", "properties"];
export const PULSE_SOURCES: SystemId[] = ["knowledge", "chat"];

const BLOCK_COPY: Record<SystemId, { name: string; kicker: string; summary: string; connects: string[] }> = {
  "investor-app": {
    name: "Investors",
    kicker: "Knowledge block",
    summary: "Repeat buyers, portfolio owners, and the attention they already show in the investor app.",
    connects: ["Intelligence Worker", "Company intelligence"],
  },
  properties: {
    name: "Properties",
    kicker: "Knowledge block",
    summary: "Income, spend, and risk the operator can already see in the finance cockpit.",
    connects: ["Property Insights", "Company intelligence"],
  },
  knowledge: {
    name: SYSTEMS.knowledge.name,
    kicker: "Source",
    summary: SYSTEMS.knowledge.subtitle,
    connects: ["Both workers"],
  },
  chat: {
    name: SYSTEMS.chat.name,
    kicker: "Source",
    summary: SYSTEMS.chat.subtitle,
    connects: ["Both workers"],
  },
};

export function pulseNode(id: FocusId, workerNames?: Partial<Record<WorkerId, string>>): PulseNode {
  if (id === "record") {
    return {
      id,
      kind: "record",
      name: "Joseph Mews",
      kicker: "Company intelligence",
      summary: "Shared memory of what the workers recorded — property facts and intent clusters, not a separate CRM.",
      connects: ["Investors", "Properties", "Property Insights", "Intelligence Worker"],
    };
  }
  if (isWorkerId(id)) {
    const worker = WORKERS[id];
    return {
      id,
      kind: "worker",
      name: workerNames?.[id] ?? worker.name,
      kicker: "Worker",
      summary: worker.purpose,
      connects: worker.writes.map((item) => item.title),
    };
  }
  const copy = BLOCK_COPY[id];
  return {
    id,
    kind: copy.kicker === "Source" ? "source" : "block",
    name: copy.name,
    kicker: copy.kicker,
    summary: copy.summary,
    connects: copy.connects,
  };
}

export const MAP_LAYOUT: Record<FocusId, { x: string; y: string }> = {
  record: { x: "50%", y: "46%" },
  "investor-app": { x: "18%", y: "32%" },
  properties: { x: "82%", y: "32%" },
  "intent-intelligence": { x: "28%", y: "78%" },
  "property-insights": { x: "72%", y: "78%" },
  knowledge: { x: "8%", y: "68%" },
  chat: { x: "92%", y: "68%" },
};

export const MAP_EDGES: [FocusId, FocusId][] = [
  ["investor-app", "record"],
  ["properties", "record"],
  ["intent-intelligence", "record"],
  ["property-insights", "record"],
  ["intent-intelligence", "investor-app"],
  ["property-insights", "properties"],
  ["knowledge", "intent-intelligence"],
  ["knowledge", "property-insights"],
  ["chat", "intent-intelligence"],
  ["chat", "property-insights"],
];
