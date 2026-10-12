import { isWorkerId, type FocusId, type WorkerId } from "@/components/intelligence-layer/model";
import { isFocus } from "./focus";

export type BlockId = "investors" | "properties";
export type AgentPane = "conversations" | "learning" | "outcomes";
export type BlockPane = "overview" | "activity" | "learning" | "outcomes";
export type PulsePane = AgentPane | BlockPane;
export type PulseSheet = "claude" | "value";

export type PulseNav = {
  block: BlockId | null;
  worker: WorkerId | null;
  pane: PulsePane;
  detail: string | null;
  focus: FocusId | null;
  sheet: PulseSheet | null;
};

export const BLOCK_IDS: BlockId[] = ["investors", "properties"];
export const PANES: AgentPane[] = ["conversations", "learning", "outcomes"];
export const BLOCK_PANES: BlockPane[] = ["overview", "activity", "learning", "outcomes"];

export function isBlockId(value: string | null): value is BlockId {
  return !!value && BLOCK_IDS.includes(value as BlockId);
}

export function isAgentPane(value: string | null): value is AgentPane {
  return !!value && PANES.includes(value as AgentPane);
}

export function isBlockPane(value: string | null): value is BlockPane {
  return !!value && BLOCK_PANES.includes(value as BlockPane);
}

export function blockPane(pane: PulsePane): BlockPane {
  return isBlockPane(pane) ? pane : "overview";
}

export function agentPane(pane: PulsePane): AgentPane {
  return isAgentPane(pane) ? pane : "conversations";
}

export function blockForWorker(id: WorkerId): BlockId {
  return id === "property-insights" ? "properties" : "investors";
}

export function blockFromFocus(id: FocusId): BlockId | null {
  if (id === "investor-app") return "investors";
  if (id === "properties") return "properties";
  if (isWorkerId(id)) return blockForWorker(id);
  return null;
}

function coercePane(worker: WorkerId | null, pane: PulsePane): PulsePane {
  if (worker) {
    if (pane === "overview" || pane === "activity") return "conversations";
    return isAgentPane(pane) ? pane : "conversations";
  }
  if (pane === "conversations") return "overview";
  return isBlockPane(pane) ? pane : "overview";
}

export function parsePulseNav(params: URLSearchParams): PulseNav {
  const focusRaw = params.get("focus");
  const blockParam = params.get("block");
  const workerParam = params.get("worker");
  const worker = isWorkerId(workerParam ?? "") ? (workerParam as WorkerId) : null;
  const block = isBlockId(blockParam) ? blockParam : worker ? blockForWorker(worker) : null;
  const drillOpen = Boolean(block || worker);
  const focus: FocusId | null = drillOpen ? null : isFocus(focusRaw) ? focusRaw : null;
  const sheetRaw = params.get("sheet");
  const paneRaw = params.get("pane");
  const pane = worker
    ? (isAgentPane(paneRaw) ? paneRaw : "conversations")
    : block
      ? (isBlockPane(paneRaw) ? paneRaw : "overview")
      : "overview";
  return {
    block,
    worker,
    pane,
    detail: params.get("detail"),
    focus,
    sheet: sheetRaw === "claude" || sheetRaw === "value" ? sheetRaw : null,
  };
}

export function writePulseQuery(nav: PulseNav, current: URLSearchParams, keep: string[] = ["demo", "step"]) {
  const query = new URLSearchParams();
  for (const key of keep) {
    const value = current.get(key);
    if (value) query.set(key, value);
  }
  if (nav.block) query.set("block", nav.block);
  if (nav.worker) query.set("worker", nav.worker);
  if (nav.worker && isAgentPane(nav.pane) && nav.pane !== "conversations") query.set("pane", nav.pane);
  if (!nav.worker && nav.block && isBlockPane(nav.pane) && nav.pane !== "overview") query.set("pane", nav.pane);
  if (nav.detail) query.set("detail", nav.detail);
  if (nav.sheet) query.set("sheet", nav.sheet);
  if (!nav.block && !nav.worker && nav.focus) query.set("focus", nav.focus);
  return query;
}

export function mergeNav(current: PulseNav, next: Partial<PulseNav>): PulseNav {
  const block = next.block === undefined ? current.block : next.block;
  const worker = next.worker === undefined ? current.worker : next.worker;
  const detail = next.detail === undefined ? current.detail : next.detail;
  const moved = next.block !== undefined || next.worker !== undefined || next.detail !== undefined;
  let pane = next.pane ?? current.pane;
  if (next.pane === undefined) {
    const openingWorker = Boolean(worker) && !current.worker;
    const closingWorker = !worker && Boolean(current.worker);
    if (openingWorker) {
      pane = current.pane === "learning" || current.pane === "outcomes" ? current.pane : "conversations";
    } else if (closingWorker) {
      pane = current.pane === "learning" || current.pane === "outcomes" ? current.pane : "overview";
    }
  }
  return {
    block,
    worker,
    pane: coercePane(worker, pane),
    detail,
    focus: next.focus === undefined ? current.focus : next.focus,
    sheet: next.sheet !== undefined ? next.sheet : moved ? null : current.sheet,
  };
}
