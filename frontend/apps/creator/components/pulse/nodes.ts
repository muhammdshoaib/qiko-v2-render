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
    name: "Investor Concierge",
    kicker: "Knowledge block · Intent Signal Agent",
    summary: "Intent signals and reachouts from investor-app activity.",
    connects: ["Investor Concierge", "Company intelligence"],
  },
  properties: {
    name: "Portfolio Reporter",
    kicker: "Knowledge block · Portfolio Insights",
    summary: "Portfolio insight cards from advised investors’ holdings.",
    connects: ["Portfolio Reporter", "Company intelligence"],
  },
  knowledge: {
    name: SYSTEMS.knowledge.name,
    kicker: "Source",
    summary: SYSTEMS.knowledge.subtitle,
    connects: ["Both knowledge blocks"],
  },
  chat: {
    name: SYSTEMS.chat.name,
    kicker: "Source",
    summary: SYSTEMS.chat.subtitle,
    connects: ["Both knowledge blocks"],
  },
};

export function pulseNode(id: FocusId, workerNames?: Partial<Record<WorkerId, string>>): PulseNode {
  if (id === "record") {
    return {
      id,
      kind: "record",
      name: "Joseph Mews",
      kicker: "Company intelligence",
      summary: "Shared record across knowledge blocks.",
      connects: ["Investor Concierge", "Portfolio Reporter"],
    };
  }
  if (isWorkerId(id)) {
    const worker = WORKERS[id];
    return {
      id,
      kind: "worker",
      name: workerNames?.[id] ?? worker.name,
      kicker: "Knowledge block",
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
  record: { x: "50%", y: "52%" },
  "investor-app": { x: "24%", y: "28%" },
  properties: { x: "76%", y: "28%" },
  "intent-intelligence": { x: "26%", y: "78%" },
  "property-insights": { x: "74%", y: "78%" },
  knowledge: { x: "10%", y: "68%" },
  chat: { x: "90%", y: "68%" },
};

/** Knowledge-block circles on the Pulse map (one block = one worker). */
export const MAP_NODES: FocusId[] = [
  "investor-app",
  "properties",
];

export const MAP_EDGES: [FocusId, FocusId][] = [
  ["investor-app", "record"],
  ["properties", "record"],
];
