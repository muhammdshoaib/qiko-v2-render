"use client";

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { BookOpen, Building2, Maximize2, MessageSquare, Minus, Plus, Radar } from "lucide-react";
import { Button, Input, cn } from "@qiko/ui";
import { toast } from "sonner";
import {
  CAPTURED_DECISIONS,
  EDGE_KIND_LABEL,
  MONTHLY_DECISIONS,
  SYSTEMS,
  WORKERS,
  isWorkerId,
  type EdgeKind,
  type FocusId,
  type SystemId,
  type WorkerId,
} from "./model";
import {
  BOARD_NODES,
  DEFAULT_VIEWPORT,
  GRID_SIZE,
  MAX_ZOOM,
  MIN_ZOOM,
  WIRE_DOT,
  WIRE_STROKE,
  WIRE_TEXT,
  ZOOM_STEP,
  clampZoom,
  curve,
  useWorkflowBoard,
  type BoardEdge,
  type Point,
  type Viewport,
  type WireColor,
} from "./workflow-board";

const NODE_ICONS: Record<SystemId, typeof BookOpen> = {
  properties: Building2,
  "investor-app": Radar,
  knowledge: BookOpen,
  chat: MessageSquare,
};

const KINDS = Object.keys(EDGE_KIND_LABEL) as EdgeKind[];
const COLORS: WireColor[] = ["cyan", "emerald", "amber", "red", "violet", "slate"];
const SNAP_SCREEN = 52;

type HandleSide = "in" | "out";
type Gesture =
  | { type: "pending"; id: FocusId; start: Point; origin: Point }
  | { type: "drag"; id: FocusId; start: Point; origin: Point }
  | { type: "pan"; start: Point; origin: Point }
  | { type: "connect"; from: FocusId; side: HandleSide; pointer: Point; snap: { id: FocusId; side: HandleSide } | null };

export function NetworkCanvas({
  focus,
  edgeId,
  pulseEdge,
  capturedCount = CAPTURED_DECISIONS,
  onFocus,
  onSelectEdge,
  onClear,
}: {
  focus: FocusId | null;
  edgeId: string | null;
  pulseEdge: string | null;
  capturedCount?: number;
  onFocus: (id: FocusId) => void;
  onSelectEdge: (id: string) => void;
  onClear: () => void;
}) {
  const board = useWorkflowBoard();
  const boardRef = useRef(board);
  boardRef.current = board;
  const canvasRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Partial<Record<FocusId, HTMLElement | null>>>({});
  const persistTimer = useRef<number>(0);
  const didPan = useRef(false);
  const [gesture, setGesture] = useState<Gesture | null>(null);
  const [camera, setCamera] = useState<Viewport>(DEFAULT_VIEWPORT);
  const [draft, setDraft] = useState<Partial<Record<FocusId, Point>>>({});
  const [tick, setTick] = useState(0);
  const [editable, setEditable] = useState(false);
  const didFit = useRef(false);
  const cameraRef = useRef(camera);
  const draftRef = useRef(draft);
  cameraRef.current = camera;
  draftRef.current = draft;
  const selected = board.edgeById(edgeId) ?? null;
  const related = relatedEdges(focus, board.edges);
  const positions = { ...board.positions, ...draft };
  const positionsRef = useRef(positions);
  positionsRef.current = positions;

  useEffect(() => {
    if (board.ready) setCamera(board.viewport);
  }, [board.ready]);

  useEffect(() => {
    const refresh = () => setTick((value) => value + 1);
    refresh();
    window.addEventListener("resize", refresh);
    return () => window.removeEventListener("resize", refresh);
  }, [board.positions, board.ready, camera.zoom]);

  const commitCamera = (next: Viewport, immediate = false) => {
    const viewport = { ...next, zoom: clampZoom(next.zoom) };
    cameraRef.current = viewport;
    setCamera(viewport);
    window.clearTimeout(persistTimer.current);
    const save = () => boardRef.current.setViewport(viewport);
    if (immediate) save();
    else persistTimer.current = window.setTimeout(save, 280);
  };

  const zoomAt = (nextZoom: number, clientX?: number, clientY?: number) => {
    const current = cameraRef.current;
    const rect = canvasRef.current?.getBoundingClientRect();
    const z = clampZoom(nextZoom);
    const cx = clientX ?? (rect ? rect.left + rect.width / 2 : 0);
    const cy = clientY ?? (rect ? rect.top + rect.height / 2 : 0);
    if (!rect) {
      commitCamera({ ...current, zoom: z }, true);
      return;
    }
    const wx = (cx - rect.left - current.x) / current.zoom;
    const wy = (cy - rect.top - current.y) / current.zoom;
    commitCamera({ x: cx - rect.left - wx * z, y: cy - rect.top - wy * z, zoom: z }, true);
  };

  const fitView = () => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const xs = BOARD_NODES.map((id) => positions[id].x);
    const ys = BOARD_NODES.map((id) => positions[id].y);
    const minX = Math.min(...xs) - 90;
    const maxX = Math.max(...xs) + 90;
    const minY = Math.min(...ys) - 70;
    const maxY = Math.max(...ys) + 70;
    const raw = Math.min((rect.width - 48) / (maxX - minX), (rect.height - 72) / (maxY - minY));
    const zoom = clampZoom(Math.min(1.05, Math.max(0.8, raw)));
    commitCamera({
      zoom,
      x: (rect.width - (maxX - minX) * zoom) / 2 - minX * zoom,
      y: (rect.height - (maxY - minY) * zoom) / 2 - minY * zoom,
    }, true);
  };

  useEffect(() => {
    if (!gesture) return;

    const move = (event: PointerEvent) => {
      const current = cameraRef.current;
      if (gesture.type === "pan") {
        if (Math.hypot(event.clientX - gesture.start.x, event.clientY - gesture.start.y) > 4) didPan.current = true;
        commitCamera({
          ...current,
          x: gesture.origin.x + (event.clientX - gesture.start.x),
          y: gesture.origin.y + (event.clientY - gesture.start.y),
        });
        return;
      }

      const pointer = clientToWorld(canvasRef.current, current, event.clientX, event.clientY);
      if (!pointer) return;

      if (gesture.type === "pending") {
        if (Math.hypot(event.clientX - gesture.start.x, event.clientY - gesture.start.y) < 5) return;
        setGesture({ type: "drag", id: gesture.id, start: gesture.start, origin: gesture.origin });
      }

      if (gesture.type === "pending" || gesture.type === "drag") {
        const startWorld = clientToWorld(canvasRef.current, current, gesture.start.x, gesture.start.y);
        if (!startWorld) return;
        setDraft((current) => ({
          ...current,
          [gesture.id]: {
            x: gesture.origin.x + pointer.x - startWorld.x,
            y: gesture.origin.y + pointer.y - startWorld.y,
          },
        }));
        return;
      }

      setGesture({
        ...gesture,
        pointer,
        snap: nearestHandle(nodeRefs.current, positionsRef.current, pointer, gesture.from, gesture.side, current.zoom),
      });
    };

    const up = () => {
      if (gesture.type === "pending") onFocus(gesture.id);
      if (gesture.type === "drag") {
        const point = draftRef.current[gesture.id];
        if (point) boardRef.current.moveNode(gesture.id, point);
        setDraft({});
      }
      if (gesture.type === "connect" && gesture.snap) {
        const from = gesture.side === "out" ? gesture.from : gesture.snap.id;
        const to = gesture.side === "out" ? gesture.snap.id : gesture.from;
        const result = boardRef.current.connect(from, to, "read");
        if (result) {
          onSelectEdge(result.edge.id);
          toast.message(result.created ? "Connection added. Prototype only — not a live permission." : "That connection already exists.");
        }
      }
      setGesture(null);
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [gesture, onFocus, onSelectEdge]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setGesture(null);
        setDraft({});
        onClear();
      }
      if (event.key === "0" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        commitCamera({ ...DEFAULT_VIEWPORT }, true);
      }
      if ((event.key === "Delete" || event.key === "Backspace") && selected && !isTyping()) {
        event.preventDefault();
        board.disconnect(selected.id);
        onClear();
        toast.message("Connection removed.");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [board, onClear, selected]);

  const startDrag = (id: FocusId, event: ReactPointerEvent) => {
    event.stopPropagation();
    if (!editable) {
      onFocus(id);
      return;
    }
    setGesture({ type: "pending", id, start: { x: event.clientX, y: event.clientY }, origin: positions[id] });
  };

  useEffect(() => {
    if (!board.ready || didFit.current) return;
    didFit.current = true;
    commitCamera({ ...DEFAULT_VIEWPORT }, true);
  }, [board.ready]);

  const startConnect = (id: FocusId, side: HandleSide, event: ReactPointerEvent) => {
    event.stopPropagation();
    const pointer = clientToWorld(canvasRef.current, camera, event.clientX, event.clientY);
    if (!pointer) return;
    setGesture({ type: "connect", from: id, side, pointer, snap: null });
  };

  useEffect(() => {
    const node = canvasRef.current;
    if (!node || !board.ready) return;
    const onWheelNative = (event: WheelEvent) => {
      event.preventDefault();
      const factor = event.deltaY > 0 ? 1 / ZOOM_STEP : ZOOM_STEP;
      zoomAt(cameraRef.current.zoom * factor, event.clientX, event.clientY);
    };
    node.addEventListener("wheel", onWheelNative, { passive: false });
    return () => node.removeEventListener("wheel", onWheelNative);
  }, [board.ready]);

  void tick;

  if (!board.ready) {
    return <div className="min-h-[420px] flex-1 animate-pulse rounded-2xl bg-card sm:min-h-[540px]" aria-busy="true" aria-label="Loading workflow board" />;
  }

  return (
    <div
      ref={canvasRef}
      className={cn(
        "relative min-h-[420px] flex-1 overflow-hidden rounded-2xl border border-border bg-card sm:min-h-[540px]",
        gesture?.type === "pan" ? "cursor-grabbing" : "cursor-grab",
      )}
      onClick={() => {
        if (didPan.current) {
          didPan.current = false;
          return;
        }
        onClear();
      }}
      onPointerDown={(event) => {
        if (event.target !== event.currentTarget && !(event.target as HTMLElement).dataset.boardBackground) return;
        didPan.current = false;
        setGesture({ type: "pan", start: { x: event.clientX, y: event.clientY }, origin: { x: camera.x, y: camera.y } });
      }}
    >
      <div
        data-board-background="true"
        className="pointer-events-auto absolute inset-0"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.14) 1.1px, transparent 0)",
          backgroundSize: `${GRID_SIZE * camera.zoom}px ${GRID_SIZE * camera.zoom}px`,
          backgroundPosition: `${camera.x}px ${camera.y}px`,
        }}
      />

      <div
        className="absolute left-0 top-0 will-change-transform"
        style={{
          transform: `translate(${camera.x}px, ${camera.y}px) scale(${camera.zoom})`,
          transformOrigin: "0 0",
        }}
      >
        <svg className="pointer-events-none absolute left-0 top-0 overflow-visible" width="1" height="1" role="img" aria-label="Workflow board">
          {board.edges.map((edge) => {
            const start = handlePoint(nodeRefs.current, edge.from, "out", positions[edge.from]);
            const end = handlePoint(nodeRefs.current, edge.to, "in", positions[edge.to]);
            const color = board.wireColor(edge);
            const active = related.has(edge.id);
            const isLive = edgeId === edge.id || pulseEdge === edge.id;
            return (
              <path
                key={edge.id}
                d={curve(start, end)}
                className={cn(
                  "fill-none stroke-[2.5] transition-opacity duration-200 motion-reduce:transition-none",
                  WIRE_STROKE[color],
                  (edge.kind === "blocked" || color === "red") && "[stroke-dasharray:18_14]",
                  isLive && "stroke-[4] opacity-100 [stroke-dasharray:12_16] [animation:qiko-flow_1.4s_linear_infinite] motion-reduce:animate-none",
                  !isLive && active && "opacity-80",
                  !active && "opacity-10",
                )}
              />
            );
          })}
          {gesture?.type === "connect" && (
            <path
              d={curve(
                handlePoint(nodeRefs.current, gesture.from, gesture.side, positions[gesture.from]),
                gesture.snap
                  ? handlePoint(nodeRefs.current, gesture.snap.id, gesture.snap.side, positions[gesture.snap.id])
                  : gesture.pointer,
              )}
              className="fill-none stroke-[3] stroke-cyan-300 [stroke-dasharray:10_12] [animation:qiko-flow_0.9s_linear_infinite] motion-reduce:animate-none"
            />
          )}
        </svg>

        <svg className="pointer-events-none absolute left-0 top-0 overflow-visible" width="1" height="1">
          {board.edges.map((edge) => {
            const start = handlePoint(nodeRefs.current, edge.from, "out", positions[edge.from]);
            const end = handlePoint(nodeRefs.current, edge.to, "in", positions[edge.to]);
            return (
              <path
                key={`${edge.id}-hit`}
                d={curve(start, end)}
                className="pointer-events-auto cursor-pointer fill-none stroke-transparent stroke-[28]"
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectEdge(edge.id);
                }}
              >
                <title>{`${EDGE_KIND_LABEL[edge.kind]}: ${edge.label}`}</title>
              </path>
            );
          })}
        </svg>

        {BOARD_NODES.map((id) => {
        const pos = positions[id];
        const connecting = gesture?.type === "connect" && gesture.from !== id;
        const snapIn = connecting && gesture.side === "out" && gesture.snap?.id === id;
        const snapOut = connecting && gesture.side === "in" && gesture.snap?.id === id;
        return (
          <div
            key={id}
            ref={(node) => {
              nodeRefs.current[id] = node;
            }}
            style={{ left: pos.x, top: pos.y }}
            className="absolute z-10 -translate-x-1/2 -translate-y-1/2"
            onClick={(event) => event.stopPropagation()}
          >
            {editable && (
            <Handle
              side="in"
              hot={Boolean(connecting && gesture.side === "out")}
              snapped={Boolean(snapIn)}
              onPointerDown={(event) => startConnect(id, "in", event)}
            />
            )}
            {isWorkerId(id) ? (
              <AgentNode
                workerId={id}
                selected={focus === id}
                dimmed={isDimmed(focus, id, board.edges)}
                onPointerDown={(event) => startDrag(id, event)}
              />
            ) : id === "record" ? (
              <RecordNode
                selected={focus === id}
                dimmed={isDimmed(focus, id, board.edges)}
                capturedCount={capturedCount}
                onPointerDown={(event) => startDrag(id, event)}
              />
            ) : (
              <SystemNode
                id={id as SystemId}
                selected={focus === id}
                dimmed={isDimmed(focus, id, board.edges)}
                onPointerDown={(event) => startDrag(id, event)}
              />
            )}
            {editable && (
            <Handle
              side="out"
              hot={Boolean(connecting && gesture.side === "in")}
              snapped={Boolean(snapOut)}
              onPointerDown={(event) => startConnect(id, "out", event)}
            />
            )}
          </div>
        );
      })}
      </div>

      <div className="absolute right-3 top-3 z-30 flex flex-col overflow-hidden rounded-xl border border-border bg-card" onPointerDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()}>
        <button type="button" aria-label="Zoom in" disabled={camera.zoom >= MAX_ZOOM} onClick={(event) => { event.stopPropagation(); zoomAt(camera.zoom * ZOOM_STEP); }} className="flex size-10 items-center justify-center text-slate-700 hover:bg-muted disabled:text-slate-600">
          <Plus className="size-4" />
        </button>
        <button type="button" aria-label="Reset zoom to 100 percent" onClick={(event) => { event.stopPropagation(); commitCamera({ ...DEFAULT_VIEWPORT }, true); }} className="flex h-9 items-center justify-center border-y border-border px-2 text-[11px] text-slate-600 hover:bg-muted">
          {Math.round(camera.zoom * 100)}%
        </button>
        <button type="button" aria-label="Zoom out" disabled={camera.zoom <= MIN_ZOOM} onClick={(event) => { event.stopPropagation(); zoomAt(camera.zoom / ZOOM_STEP); }} className="flex size-10 items-center justify-center text-slate-700 hover:bg-muted disabled:text-slate-600">
          <Minus className="size-4" />
        </button>
        <button type="button" aria-label="Fit all nodes" onClick={(event) => { event.stopPropagation(); fitView(); }} className="flex size-10 items-center justify-center border-t border-border text-slate-700 hover:bg-muted">
          <Maximize2 className="size-3.5" />
        </button>
      </div>

      {editable && selected && (
        <WireEditor
          edge={selected}
          color={board.wireColor(selected)}
          onChange={(patch) => board.updateEdge(selected.id, patch)}
          onDisconnect={() => {
            board.disconnect(selected.id);
            onClear();
            toast.message("Connection removed.");
          }}
        />
      )}

      {board.edges.length === 0 && (
        <p className="pointer-events-none absolute inset-x-8 top-1/2 -translate-y-1/2 text-center text-sm text-slate-500">
          No connections. Drag a handle on a node to a glowing target.
        </p>
      )}

      <div className="absolute bottom-0 left-0 right-0 z-20 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border bg-card/95 px-3 py-2 text-[10px] text-slate-500">
        {KINDS.map((kind) => (
          <span key={kind} className={WIRE_TEXT[board.wireColor({ kind, id: kind, from: "property-insights", to: "properties", label: "", rule: "", example: "" })]}>
            {EDGE_KIND_LABEL[kind]}
          </span>
        ))}
        <span className="ml-auto flex gap-2">
          <Button type="button" size="sm" variant="outline" className="h-8 text-[11px]" aria-pressed={editable} onClick={(event) => { event.stopPropagation(); setEditable((value) => !value); }}>
            {editable ? "Done arranging" : "Arrange"}
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-8 text-[11px]" onClick={(event) => { event.stopPropagation(); board.resetBoard(); commitCamera({ ...DEFAULT_VIEWPORT }, true); onClear(); }}>
            Reset
          </Button>
        </span>
      </div>
    </div>
  );
}

function Handle({
  side,
  hot,
  snapped,
  onPointerDown,
}: {
  side: HandleSide;
  hot: boolean;
  snapped: boolean;
  onPointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      type="button"
      aria-label={side === "out" ? "Drag to create a connection" : "Drop a connection here"}
      onPointerDown={onPointerDown}
      onClick={(event) => event.stopPropagation()}
      className={cn(
        "absolute top-1/2 z-20 flex size-11 -translate-y-1/2 items-center justify-center rounded-full touch-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300/70",
        side === "in" ? "left-0 -translate-x-1/2" : "right-0 translate-x-1/2",
      )}
    >
      <span
        className={cn(
          "size-3 rounded-full border-2 bg-card transition-transform",
          hot ? "border-cyan-300" : "border-slate-500",
          snapped && "scale-150 border-cyan-200 bg-indigo-500",
        )}
      />
    </button>
  );
}

function AgentNode({
  workerId,
  selected,
  dimmed,
  onPointerDown,
}: {
  workerId: WorkerId;
  selected: boolean;
  dimmed: boolean;
  onPointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
}) {
  const worker = WORKERS[workerId];
  const size = 112 + Math.round(Math.min(worker.decisions, 24) * 1.4);
  return (
    <button
      type="button"
      aria-pressed={selected}
      onPointerDown={onPointerDown}
      onClick={(event) => event.stopPropagation()}
      style={{ width: size, height: size }}
      className={cn(
        "rounded-full border bg-card text-left shadow-[0_0_60px_-18px_rgba(34,211,238,0.55)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300/70",
        selected ? "border-cyan-300/70 ring-2 ring-cyan-400/20" : "border-border",
        dimmed && "opacity-40",
      )}
    >
      <span className="flex h-full flex-col items-center justify-center px-3 text-center">
        <span className="text-[10px] uppercase tracking-wider text-indigo-600">Worker</span>
        <span className="mt-1 text-[13px] font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{worker.name}</span>
        <span className="mt-2 text-xl font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{worker.decisions}</span>
        <span className="text-[10px] text-slate-500">outcomes</span>
      </span>
    </button>
  );
}

function RecordNode({
  selected,
  dimmed,
  capturedCount,
  onPointerDown,
}: {
  selected: boolean;
  dimmed: boolean;
  capturedCount: number;
  onPointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onPointerDown={onPointerDown}
      onClick={(event) => event.stopPropagation()}
      className={cn(
        "relative flex size-[168px] items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300/70",
        dimmed && "opacity-40",
      )}
    >
      {MONTHLY_DECISIONS.map((month, index) => (
        <span
          key={month.month}
          className={cn(
            "absolute rounded-full border border-indigo-400/25 motion-reduce:animate-none",
            selected ? "animate-[pulse_3s_ease-in-out_infinite]" : "[animation:qiko-breathe_4.8s_ease-in-out_infinite]",
          )}
          style={{ width: 92 + index * 22, height: 92 + index * 22, opacity: 0.22 + index * 0.12, animationDelay: `${index * 180}ms` }}
          title={`${month.month}: ${month.value} captured decisions`}
        />
      ))}
      <span className={cn("relative flex size-[88px] flex-col items-center justify-center rounded-full border bg-card", selected ? "border-indigo-300/70" : "border-border")}>
        <span className="text-[10px] uppercase tracking-wider text-indigo-600">Company</span>
        <span className="text-sm font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>Qiko</span>
        <span className="text-[10px] text-slate-500">{capturedCount}</span>
      </span>
      <span className="sr-only">Qiko company record. Rings are monthly captured decisions. Prototype data.</span>
    </button>
  );
}

function SystemNode({
  id,
  selected,
  dimmed,
  onPointerDown,
}: {
  id: SystemId;
  selected: boolean;
  dimmed: boolean;
  onPointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
}) {
  const system = SYSTEMS[id];
  const Icon = NODE_ICONS[id];
  return (
    <button
      type="button"
      aria-pressed={selected}
      onPointerDown={onPointerDown}
      onClick={(event) => event.stopPropagation()}
      className={cn(
        "flex min-w-[132px] max-w-[168px] items-center gap-2 rounded-xl border bg-card px-2.5 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 sm:min-w-[150px]",
        selected ? "border-border" : "border-border",
        dimmed && "opacity-35",
      )}
    >
      <Icon className="size-4 shrink-0 text-slate-600" />
      <span>
        <span className="block text-[13px] font-medium text-foreground">{system.name}</span>
        <span className="block text-[11px] text-slate-500">{system.subtitle}</span>
      </span>
    </button>
  );
}

function WireEditor({
  edge,
  color,
  onChange,
  onDisconnect,
}: {
  edge: BoardEdge;
  color: WireColor;
  onChange: (patch: Partial<Pick<BoardEdge, "kind" | "label" | "color">>) => void;
  onDisconnect: () => void;
}) {
  return (
    <div
      className="absolute left-1/2 top-3 z-30 w-[min(94%,420px)] -translate-x-1/2 rounded-xl border border-border bg-card p-3 shadow-lg"
      onClick={(event) => event.stopPropagation()}
    >
      <p className={cn("text-[10px] uppercase tracking-wider", WIRE_TEXT[color])}>{EDGE_KIND_LABEL[edge.kind]}</p>
      <Input
        aria-label="Connection label"
        value={edge.label}
        onChange={(event) => onChange({ label: event.target.value })}
        className="mt-2 h-9 bg-card text-sm"
      />
      <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="Connection type">
        {KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            aria-pressed={edge.kind === kind}
            onClick={() => onChange({ kind })}
            className={cn(
              "min-h-9 rounded-lg px-2.5 text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300",
              edge.kind === kind ? "bg-slate-100 text-foreground" : "text-slate-500 hover:text-foreground",
            )}
          >
            {EDGE_KIND_LABEL[kind]}
          </button>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2" role="group" aria-label="Wire colour">
        {COLORS.map((item) => (
          <button
            key={item}
            type="button"
            aria-label={`Set colour ${item}`}
            aria-pressed={color === item}
            onClick={() => onChange({ color: item })}
            className={cn(
              "size-7 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white",
              WIRE_DOT[item],
              color === item && "ring-2 ring-white",
            )}
          />
        ))}
        <Button type="button" size="sm" variant="outline" className="ml-auto" onClick={onDisconnect}>
          Disconnect
        </Button>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">Prototype board. Changing a wire does not change live permissions.</p>
    </div>
  );
}

function connectedIds(focus: FocusId, edges: BoardEdge[]) {
  const ids = new Set<FocusId>([focus]);
  for (const edge of edges) {
    if (edge.from === focus || edge.to === focus) {
      ids.add(edge.from);
      ids.add(edge.to);
    }
  }
  return ids;
}

function relatedEdges(focus: FocusId | null, edges: BoardEdge[]) {
  if (!focus) {
    return new Set(edges.filter((edge) => edge.from === "record" || edge.to === "record").map((edge) => edge.id));
  }
  return new Set(edges.filter((edge) => edge.from === focus || edge.to === focus).map((edge) => edge.id));
}

function isDimmed(focus: FocusId | null, id: FocusId, edges: BoardEdge[]) {
  if (!focus) return false;
  return !connectedIds(focus, edges).has(id);
}

function isTyping() {
  const node = document.activeElement;
  return node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement;
}

function clientToWorld(canvas: HTMLDivElement | null, camera: Viewport, clientX: number, clientY: number): Point | null {
  if (!canvas) return null;
  const rect = canvas.getBoundingClientRect();
  return {
    x: (clientX - rect.left - camera.x) / camera.zoom,
    y: (clientY - rect.top - camera.y) / camera.zoom,
  };
}

function handlePoint(
  refs: Partial<Record<FocusId, HTMLElement | null>>,
  id: FocusId,
  side: HandleSide,
  origin: Point,
): Point {
  const node = refs[id];
  const width = node?.offsetWidth ?? 160;
  return {
    x: origin.x + (side === "out" ? width / 2 : -width / 2),
    y: origin.y,
  };
}

function nearestHandle(
  refs: Partial<Record<FocusId, HTMLElement | null>>,
  positions: Record<FocusId, Point>,
  pointer: Point,
  from: FocusId,
  fromSide: HandleSide,
  zoom: number,
) {
  const need: HandleSide = fromSide === "out" ? "in" : "out";
  let best: { id: FocusId; side: HandleSide } | null = null;
  let distance = SNAP_SCREEN / zoom;
  for (const id of BOARD_NODES) {
    if (id === from) continue;
    const point = handlePoint(refs, id, need, positions[id]);
    const next = Math.hypot(point.x - pointer.x, point.y - pointer.y);
    if (next < distance) {
      distance = next;
      best = { id, side: need };
    }
  }
  return best;
}
