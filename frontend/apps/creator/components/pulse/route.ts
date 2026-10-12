import { isWorkerId, type FocusId, type WorkerId } from "@/components/intelligence-layer/model";

export type BlockId = "investors" | "properties";
export type AgentPane = "conversations" | "learning" | "outcomes";
export type PulseSheet = "claude" | "value";

export type PulseNav = {
  block: BlockId | null;
  worker: WorkerId | null;
  pane: AgentPane;
  detail: string | null;
  focus: FocusId | null;
  sheet: PulseSheet | null;
};

export const BLOCK_IDS: BlockId[] = ["investors", "properties"];
export const PANES: AgentPane[] = ["conversations", "learning", "outcomes"];

export function isBlockId(value: string | null): value is BlockId {
  return !!value && BLOCK_IDS.includes(value as BlockId);
}

export function isAgentPane(value: string | null): value is AgentPane {
  return !!value && PANES.includes(value as AgentPane);
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

export function parsePulseNav(params: URLSearchParams): PulseNav {
  const focusRaw = params.get("focus");
  const blockParam = params.get("block");
  const workerParam = params.get("worker");
  const worker = isWorkerId(workerParam) ? workerParam : isWorkerId(focusRaw ?? "") ? (focusRaw as WorkerId) : null;
  const block = isBlockId(blockParam)
    ? blockParam
    : worker
      ? blockForWorker(worker)
      : focusRaw === "investor-app"
        ? "investors"
        : focusRaw === "properties"
          ? "properties"
          : null;
  const drillOpen = Boolean(block || worker);
  const focus: FocusId | null = drillOpen
    ? null
    : focusRaw && focusRaw !== "none" && (focusRaw === "record" || focusRaw === "knowledge" || focusRaw === "chat")
      ? focusRaw
      : null;
  const sheetRaw = params.get("sheet");
  return {
    block,
    worker,
    pane: isAgentPane(params.get("pane")) ? (params.get("pane") as AgentPane) : "conversations",
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
  if (nav.worker && nav.pane !== "conversations") query.set("pane", nav.pane);
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
  return {
    block,
    worker,
    pane: next.pane ?? current.pane,
    detail,
    focus: next.focus === undefined ? current.focus : next.focus,
    sheet: next.sheet !== undefined ? next.sheet : moved ? null : current.sheet,
  };
}
