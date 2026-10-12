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
    summary: "Repeat attention, referred arrivals, and quiet listings — knowledge the Intelligence Worker may read and record.",
    connects: ["Intelligence Worker", "Company intelligence"],
  },
  properties: {
    name: "Properties",
    kicker: "Knowledge block",
    summary: "Income, spend, and risk already visible in the finance cockpit — notes, not a second ledger.",
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
      summary: "Shared memory of recorded notes and decisions from Investors and Properties — not a score, and not a CRM.",
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
  record: { x: "50%", y: "48%" },
  "investor-app": { x: "22%", y: "22%" },
  properties: { x: "78%", y: "22%" },
  "intent-intelligence": { x: "24%", y: "82%" },
  "property-insights": { x: "76%", y: "82%" },
  knowledge: { x: "10%", y: "68%" },
  chat: { x: "90%", y: "68%" },
};

export const MAP_NODES: FocusId[] = [
  "record",
  "investor-app",
  "properties",
  "intent-intelligence",
  "property-insights",
];

export const MAP_EDGES: [FocusId, FocusId][] = [
  ["investor-app", "record"],
  ["properties", "record"],
  ["intent-intelligence", "investor-app"],
  ["property-insights", "properties"],
  ["intent-intelligence", "record"],
  ["property-insights", "record"],
];
