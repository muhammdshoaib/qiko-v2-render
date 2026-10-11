"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { EDGES, EDGE_KIND_LABEL, type EdgeKind, type FocusId, type GraphEdge } from "./model";

export const BOARD_NODES: FocusId[] = ["property-insights", "intent-intelligence", "record", "properties", "investor-app", "knowledge", "chat"];
export type WireColor = "cyan" | "emerald" | "amber" | "red" | "violet" | "slate";
export type Point = { x: number; y: number };
export type BoardEdge = Omit<GraphEdge, "id"> & { id: string; color?: WireColor };

const STORAGE_KEY = "qiko-studio-board-v3";
export const MIN_ZOOM = 0.35;
export const MAX_ZOOM = 2.4;
export const ZOOM_STEP = 1.18;
export const GRID_SIZE = 22;

export type Viewport = { x: number; y: number; zoom: number };

export const DEFAULT_VIEWPORT: Viewport = { x: 24, y: 16, zoom: 1 };

export const DEFAULT_POSITIONS: Record<FocusId, Point> = {
  record: { x: 300, y: 220 },
  "property-insights": { x: 120, y: 220 },
  "intent-intelligence": { x: 480, y: 220 },
  properties: { x: 70, y: 80 },
  knowledge: { x: 300, y: 58 },
  "investor-app": { x: 530, y: 80 },
  chat: { x: 300, y: 380 },
};

export const KIND_COLOR: Record<EdgeKind, WireColor> = {
  read: "cyan",
  write: "emerald",
  review: "amber",
  blocked: "red",
  handoff: "violet",
};

export const WIRE_STROKE: Record<WireColor, string> = {
  cyan: "stroke-cyan-400",
  emerald: "stroke-emerald-400",
  amber: "stroke-amber-400",
  red: "stroke-red-400",
  violet: "stroke-violet-400",
  slate: "stroke-slate-400",
};

export const WIRE_TEXT: Record<WireColor, string> = {
  cyan: "text-cyan-300",
  emerald: "text-emerald-300",
  amber: "text-amber-300",
  red: "text-red-300",
  violet: "text-violet-300",
  slate: "text-slate-300",
};

export const WIRE_DOT: Record<WireColor, string> = {
  cyan: "bg-cyan-400",
  emerald: "bg-emerald-400",
  amber: "bg-amber-400",
  red: "bg-red-400",
  violet: "bg-violet-400",
  slate: "bg-slate-400",
};

type BoardState = {
  positions: Record<FocusId, Point>;
  edges: BoardEdge[];
  viewport: Viewport;
};

type BoardApi = BoardState & {
  ready: boolean;
  moveNode: (id: FocusId, point: Point) => void;
  setViewport: (viewport: Viewport) => void;
  connect: (from: FocusId, to: FocusId, kind?: EdgeKind) => { edge: BoardEdge; created: boolean } | null;
  disconnect: (id: string) => void;
  updateEdge: (id: string, patch: Partial<Pick<BoardEdge, "kind" | "label" | "color">>) => void;
  resetLayout: () => void;
  resetBoard: () => void;
  edgeById: (id: string | null) => BoardEdge | undefined;
  wireColor: (edge: BoardEdge) => WireColor;
};

const BoardContext = createContext<BoardApi | null>(null);

function seed(): BoardState {
  return {
    positions: { ...DEFAULT_POSITIONS },
    edges: EDGES.map((edge) => ({ ...edge })),
    viewport: { ...DEFAULT_VIEWPORT },
  };
}

export function clampZoom(zoom: number) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}

export function WorkflowBoardProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BoardState>(seed);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<BoardState>;
        const viewport = parsed.viewport;
        setState({
          positions: { ...DEFAULT_POSITIONS, ...parsed.positions },
          edges: Array.isArray(parsed.edges) ? parsed.edges : seed().edges,
          viewport: {
            x: typeof viewport?.x === "number" && Number.isFinite(viewport.x) ? viewport.x : DEFAULT_VIEWPORT.x,
            y: typeof viewport?.y === "number" && Number.isFinite(viewport.y) ? viewport.y : DEFAULT_VIEWPORT.y,
            zoom: clampZoom(typeof viewport?.zoom === "number" && Number.isFinite(viewport.zoom) ? viewport.zoom : DEFAULT_VIEWPORT.zoom),
          },
        });
      }
    } catch {
      // Keep seed if stored JSON is unreadable.
    }
    setReady(true);
  }, []);

  const api = useMemo<BoardApi>(() => {
    const write = (next: BoardState) => {
      setState(next);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    };

    return {
      ...state,
      ready,
      moveNode: (id, point) => {
        write({ ...state, positions: { ...state.positions, [id]: point } });
      },
      setViewport: (viewport) => {
        write({ ...state, viewport: { ...viewport, zoom: clampZoom(viewport.zoom) } });
      },
      connect: (from, to, kind = "read") => {
        if (from === to) return null;
        const existing = state.edges.find((edge) => edge.from === from && edge.to === to && edge.kind === kind);
        if (existing) return { edge: existing, created: false };
        const created: BoardEdge = {
          id: `wire-${from}-${to}-${kind}-${crypto.randomUUID().slice(0, 6)}`,
          from,
          to,
          kind,
          label: EDGE_KIND_LABEL[kind],
          rule: "Prototype connection. This does not grant a live permission.",
          example: "Layout only — not a live integration.",
          color: KIND_COLOR[kind],
        };
        write({ ...state, edges: [...state.edges, created] });
        return { edge: created, created: true };
      },
      disconnect: (id) => {
        write({ ...state, edges: state.edges.filter((edge) => edge.id !== id) });
      },
      updateEdge: (id, patch) => {
        write({
          ...state,
          edges: state.edges.map((edge) => {
            if (edge.id !== id) return edge;
            const next = { ...edge, ...patch };
            if (patch.kind && !patch.color) next.color = KIND_COLOR[patch.kind];
            if (patch.kind && !patch.label) next.label = EDGE_KIND_LABEL[patch.kind];
            return next;
          }),
        });
      },
      resetLayout: () => write({ ...state, positions: { ...DEFAULT_POSITIONS }, viewport: { ...DEFAULT_VIEWPORT } }),
      resetBoard: () => write(seed()),
      edgeById: (id) => state.edges.find((edge) => edge.id === id),
      wireColor: (edge) => edge.color ?? KIND_COLOR[edge.kind],
    };
  }, [ready, state]);

  return <BoardContext.Provider value={api}>{children}</BoardContext.Provider>;
}

export function useWorkflowBoard() {
  const value = useContext(BoardContext);
  if (!value) throw new Error("useWorkflowBoard must be used inside WorkflowBoardProvider");
  return value;
}

export function curve(from: Point, to: Point) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const lift = Math.max(40, Math.abs(dx) * 0.35);
  const c1 = { x: from.x + lift, y: from.y + dy * 0.08 };
  const c2 = { x: to.x - lift, y: to.y - dy * 0.08 };
  return `M ${from.x} ${from.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${to.x} ${to.y}`;
}
