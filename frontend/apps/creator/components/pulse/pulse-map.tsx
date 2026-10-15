"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@qiko/ui";
import type { FocusId, WorkerId } from "@/components/intelligence-layer/model";
import { LIVE_CAPTURES } from "./live-captures";
import { MAP_NODES, pulseNode } from "./nodes";

type AreaId = "investor-app" | "properties";

type Area = {
  id: AreaId;
  name: string;
  live: boolean;
  dark?: boolean;
  ang: number;
  col: string;
  agents: number;
  workerLabel: string;
};

type Sys = { name: string; to: AreaId[] };
type Pt = { x: number; y: number };
type Node = { a: Area; x: number; y: number; r: number; c: string; phase: number; flash: number };
type SysN = { s: Sys; x: number; y: number };
type Part = { from: Pt; to: Node; c: Pt; t: number; sp: number; kind: "in" | "up"; col: string };

/** One knowledge block = one worker. Map shows exactly these two. */
const AREAS: Area[] = [
  { id: "investor-app", name: "Investor Concierge", workerLabel: "Intent Signal Agent", live: true, ang: -2.2, col: "#6366F1", agents: 1 },
  { id: "properties", name: "Portfolio Reporter", workerLabel: "Portfolio Insights", live: true, ang: 0.85, col: "#22D3EE", agents: 1 },
];

const SYSTEMS: Sys[] = [
  { name: "Investor app", to: ["investor-app"] },
  { name: "Investor portfolios", to: ["properties"] },
  { name: "Knowledge library", to: ["investor-app", "properties"] },
  { name: "Grounded chat", to: ["investor-app", "properties"] },
];

export function PulseMap({
  focus,
  workerNames,
  onSelect,
}: {
  focus: FocusId | null;
  workerNames?: Partial<Record<WorkerId, string>>;
  onSelect: (id: FocusId) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [hover, setHover] = useState<{
    name: string;
    lines: [string, string][];
    cta: string;
    x: number;
    y: number;
    placement: "above" | "below";
  } | null>(null);
  const mapFocus = focus && MAP_NODES.includes(focus) ? focus : null;

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let W = 0;
    let H = 0;
    let dpr = 1;
    let nodes: Node[] = [];
    let sysNodes: SysN[] = [];
    let parts: Part[] = [];
    let core: Pt = { x: 0, y: 0 };
    let hoverNode: Node | null = null;
    let zoom: { n: Node; t0: number; done: boolean } | null = null;
    let lastSpawn = 0;
    let lastEvent = 0;
    let evIdx = 4;
    let cancelled = false;

    const layout = () => {
      const box = wrap.getBoundingClientRect();
      W = box.width;
      H = box.height;
      dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      canvas.style.width = `${W}px`;
      canvas.style.height = `${H}px`;
      const cx = W / 2;
      const cy = H / 2 + 12;
      const rx = Math.min(W * 0.34, 460);
      const ry = Math.min(H * 0.32, 250);
      const base = Math.min(W, H);
      nodes = AREAS.map((a) => ({
        a,
        x: cx + Math.cos(a.ang) * rx * (a.dark ? 0.62 : 1),
        y: cy + Math.sin(a.ang) * ry * (a.dark ? 0.62 : 1),
        r: a.dark ? base * 0.042 : base * 0.082,
        c: a.col,
        phase: Math.random() * 6,
        flash: 0,
      }));
      const sx = Math.min(W * 0.44, 580);
      const sy = Math.min(H * 0.40, 290);
      sysNodes = SYSTEMS.map((s, i) => {
        const t = -Math.PI / 2 + ((i + 0.5) / SYSTEMS.length) * Math.PI * 2;
        return { s, x: cx + Math.cos(t) * sx, y: cy + Math.sin(t) * sy };
      });
      core = { x: cx, y: cy };
    };

    const spawn = () => {
      const s = sysNodes[Math.floor(Math.random() * sysNodes.length)];
      const id = s.s.to[Math.floor(Math.random() * s.s.to.length)];
      const n = nodes.find((x) => x.a.id === id);
      if (!n || n.a.dark) return;
      parts.push({ from: s, to: n, c: ctrl(s, n, 0.18), t: 0, sp: 0.005 + Math.random() * 0.006, kind: "in", col: n.c });
    };
    const spawnUp = (n: Node) => {
      parts.push({ from: n, to: n, c: ctrl(n, core, -0.12), t: 0, sp: 0.011, kind: "up", col: n.c });
    };

    const hit = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left;
      const y = e.clientY - r.top;
      if (Math.hypot(x - core.x, y - core.y) < 28) return { kind: "core" as const };
      for (const n of nodes) {
        if (Math.hypot(x - n.x, y - n.y) < n.r + 12) return { kind: "area" as const, n };
      }
      return null;
    };

    const tipPlace = (x: number, aboveAnchorY: number) => {
      // Flip below when near the top so overflow:hidden on the map does not clip the card.
      const tipH = 118;
      const tipW = 230;
      const above = aboveAnchorY >= tipH + 12;
      return {
        x: Math.min(Math.max(x, tipW / 2 + 8), Math.max(tipW / 2 + 8, W - tipW / 2 - 8)),
        placement: (above ? "above" : "below") as "above" | "below",
      };
    };

    const onMove = (e: PointerEvent) => {
      const found = hit(e);
      if (found?.kind === "area") {
        hoverNode = found.n;
        canvas.style.cursor = "pointer";
        const a = found.n.a;
        const aboveY = found.n.y - found.n.r - 8;
        const belowY = found.n.y + found.n.r + 8;
        const place = tipPlace(found.n.x, aboveY);
        setHover({
          name: a.name,
          lines:
            a.id === "investor-app"
              ? [["Role", a.workerLabel], ["High-intent", "28"], ["Reachouts awaiting", "1 of 9"]]
              : [["Role", a.workerLabel], ["With insights", "3,104"], ["Concentration cards", "412"]],
          cta: "Open knowledge block →",
          x: place.x,
          y: place.placement === "above" ? aboveY : belowY,
          placement: place.placement,
        });
      } else if (found?.kind === "core") {
        hoverNode = null;
        canvas.style.cursor = "pointer";
        const place = tipPlace(core.x, core.y - 36);
        setHover({
          name: "Joseph Mews",
          lines: [["Blocks", "Investor Concierge · Portfolio Reporter"]],
          cta: "Click to open →",
          x: place.x,
          y: place.placement === "above" ? core.y - 36 : core.y + 28,
          placement: place.placement,
        });
      } else {
        hoverNode = null;
        canvas.style.cursor = "default";
        setHover(null);
      }
    };

    const onClick = (e: PointerEvent) => {
      const found = hit(e);
      if (!found) return;
      if (found.kind === "core") {
        onSelectRef.current("record");
        return;
      }
      const a = found.n.a;
      if (reduced) {
        onSelectRef.current(a.id);
        return;
      }
      setHover(null);
      zoom = { n: found.n, t0: performance.now(), done: false };
    };

    const draw = (ts: number) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      if (zoom) {
        const p = Math.min(1, (ts - zoom.t0) / 520);
        const ease = 1 - (1 - p) ** 3;
        const sc = 1 + ease * 2.2;
        ctx.translate(W / 2, H / 2);
        ctx.scale(sc, sc);
        ctx.translate(-W / 2 + (W / 2 - zoom.n.x) * ease, -H / 2 + (H / 2 - zoom.n.y) * ease);
        if (p >= 1 && !zoom.done) {
          zoom.done = true;
          const id = zoom.n.a.id;
          setTimeout(() => onSelectRef.current(id), 40);
        }
      }
      const tint = ctx.createRadialGradient(core.x, core.y, 10, core.x, core.y, Math.max(W, H) * 0.55);
      tint.addColorStop(0, "rgba(99,102,241,.10)");
      tint.addColorStop(1, "rgba(99,102,241,0)");
      ctx.fillStyle = tint;
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = "rgba(255,255,255,.08)";
      for (let x = 12; x < W; x += 22) {
        for (let y = 12; y < H; y += 22) ctx.fillRect(x, y, 1.2, 1.2);
      }
      ctx.lineWidth = 1;
      for (const s of sysNodes) {
        for (const id of s.s.to) {
          const n = nodes.find((x) => x.a.id === id);
          if (!n) continue;
          const c = ctrl(s, n, 0.18);
          const hl = hoverNode?.a.id === id;
          ctx.strokeStyle = hl ? hexA(n.c, 0.5) : "rgba(148,163,184,.18)";
          ctx.beginPath();
          ctx.moveTo(s.x, s.y);
          ctx.quadraticCurveTo(c.x, c.y, n.x, n.y);
          ctx.stroke();
        }
      }
      for (const n of nodes) {
        if (n.a.dark) continue;
        const c = ctrl(n, core, -0.12);
        ctx.strokeStyle = hexA(n.c, 0.28);
        ctx.setLineDash([2, 5]);
        ctx.beginPath();
        ctx.moveTo(n.x, n.y);
        ctx.quadraticCurveTo(c.x, c.y, core.x, core.y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      const beat = ((ts / 1000) % 2.4) / 2.4;
      for (let k = 0; k < 2; k++) {
        const p = (beat + k * 0.5) % 1;
        ctx.strokeStyle = `rgba(34,211,238,${(1 - p) * 0.28})`;
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        ctx.arc(core.x, core.y, 20 + p * 64, 0, Math.PI * 2);
        ctx.stroke();
      }
      const cg = ctx.createLinearGradient(core.x - 22, core.y - 22, core.x + 22, core.y + 22);
      cg.addColorStop(0, "#6366F1");
      cg.addColorStop(1, "#22D3EE");
      ctx.shadowColor = "rgba(99,102,241,.45)";
      ctx.shadowBlur = 22;
      ctx.fillStyle = cg;
      ctx.beginPath();
      ctx.arc(core.x, core.y, 20, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.moveTo(core.x - 9, core.y);
      ctx.lineTo(core.x - 4, core.y);
      ctx.lineTo(core.x - 1, core.y - 5);
      ctx.lineTo(core.x + 2, core.y + 5);
      ctx.lineTo(core.x + 5, core.y);
      ctx.lineTo(core.x + 9, core.y);
      ctx.stroke();
      ctx.textAlign = "center";
      ctx.font = '500 9.5px ui-monospace, "Roboto Mono", monospace';
      ctx.fillStyle = "rgba(148,163,184,.9)";
      ctx.fillText("COMPANY INTELLIGENCE", core.x, core.y + 36);

      if (!reduced) {
        for (let i = parts.length - 1; i >= 0; i--) {
          const p = parts[i];
          p.t += p.sp;
          const dest = p.kind === "in" ? p.to : core;
          const curve = p.kind === "in" ? p.c : ctrl(p.to, core, -0.12);
          if (p.t >= 1) {
            if (p.kind === "in") {
              p.to.flash = 1;
              if (Math.random() < 0.35) spawnUp(p.to);
            }
            parts.splice(i, 1);
            continue;
          }
          for (let k = 0; k < 6; k++) {
            const q = qp(p.from, curve, dest, Math.max(0, p.t - k * 0.012));
            ctx.fillStyle = hexA(p.kind === "in" ? p.col : "#22D3EE", 0.55 * (1 - k / 6));
            ctx.beginPath();
            ctx.arc(q.x, q.y, (p.kind === "in" ? 2.2 : 1.7) * (1 - k / 8), 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      ctx.font = "500 11px Inter, sans-serif";
      for (const s of sysNodes) {
        const tw = ctx.measureText(s.s.name).width + 18;
        roundRect(ctx, s.x - tw / 2, s.y - 11, tw, 22, 11);
        ctx.fillStyle = "rgba(15,23,42,.92)";
        ctx.fill();
        ctx.strokeStyle = "rgba(255,255,255,.12)";
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.fillStyle = "#94A3B8";
        ctx.fillText(s.s.name, s.x, s.y + 4);
      }

      const t = ts / 1000;
      for (const n of nodes) {
        const isH = hoverNode === n;
        const r = n.r * (1 + Math.sin(t * 1.6 + n.phase) * 0.025) * (isH ? 1.07 : 1);
        n.flash = Math.max(0, n.flash - 0.04);
        if (n.a.dark) {
          ctx.setLineDash([4, 5]);
          ctx.strokeStyle = hexA(n.c, 0.8);
          ctx.lineWidth = 1.4;
          ctx.fillStyle = hexA(n.c, 0.08);
          ctx.beginPath();
          ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
          ctx.setLineDash([]);
        } else {
          const gl = ctx.createRadialGradient(n.x, n.y, r * 0.6, n.x, n.y, r * 1.9);
          gl.addColorStop(0, hexA(n.c, 0.18 + n.flash * 0.2));
          gl.addColorStop(1, hexA(n.c, 0));
          ctx.fillStyle = gl;
          ctx.beginPath();
          ctx.arc(n.x, n.y, r * 1.9, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = "rgba(15,23,42,.92)";
          ctx.shadowColor = hexA(n.c, 0.35);
          ctx.shadowBlur = 18;
          ctx.beginPath();
          ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;
          ctx.strokeStyle = hexA(n.c, isH ? 0.95 : 0.45);
          ctx.lineWidth = isH ? 2 : 1.3;
          ctx.beginPath();
          ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
          ctx.stroke();
          for (let k = 0; k < n.a.agents; k++) {
            const ang = t * 0.5 + k * (Math.PI * 2 / Math.max(n.a.agents, 1)) + n.phase;
            const ax = n.x + Math.cos(ang) * (r + 16);
            const ay = n.y + Math.sin(ang) * (r + 16);
            ctx.fillStyle = "#0F172A";
            ctx.strokeStyle = n.c;
            ctx.lineWidth = 1.6;
            ctx.beginPath();
            ctx.arc(ax, ay, 4.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
          }
        }
        ctx.textAlign = "center";
        ctx.fillStyle = "#F8FAFC";
        ctx.font = `700 ${n.a.id === "investor-app" ? 14.5 : 12.5}px var(--font-display), Inter, sans-serif`;
        ctx.fillText(n.a.name, n.x, n.y + (n.a.dark ? 2 : -2));
        ctx.font = '500 10.5px ui-monospace, "Roboto Mono", monospace';
        if (n.a.dark) {
          ctx.fillStyle = "#E5484D";
          ctx.fillText("NOT CONNECTED", n.x, n.y + 16);
        } else {
          ctx.fillStyle = "#94A3B8";
          ctx.fillText(n.a.id === "investor-app" ? "28 high-intent" : "3,104 insights", n.x, n.y + 14);
        }
      }

      if (!zoom && !reduced && ts - lastSpawn > 170) {
        spawn();
        lastSpawn = ts;
      }
      if (!zoom && ts - lastEvent > (reduced ? 9000 : 4200)) {
        lastEvent = ts;
        const event = LIVE_CAPTURES[evIdx++ % LIVE_CAPTURES.length];
        const n = nodes.find((x) => x.a.id === event.block);
        if (n) {
          n.flash = 1;
          if (!reduced) for (let k = 0; k < 4; k++) setTimeout(() => spawnUp(n), k * 120);
        }
      }
      if (!cancelled) raf = requestAnimationFrame(draw);
    };

    layout();
    if (!reduced) for (let i = 0; i < 12; i++) spawn();
    const observer = new ResizeObserver(layout);
    observer.observe(wrap);
    const onLeave = () => {
      hoverNode = null;
      setHover(null);
      canvas.style.cursor = "default";
    };
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);
    canvas.addEventListener("click", onClick);
    raf = requestAnimationFrame(draw);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      canvas.removeEventListener("click", onClick);
    };
  }, []);

  return (
    <section aria-label="Company intelligence map" className="relative flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-white/10 bg-muted">
      <div className="pointer-events-none absolute inset-x-0 top-0 z-[1] flex items-start justify-between gap-3 p-4 sm:px-5 sm:pt-5">
        <div>
          <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
            Knowledge map
          </h2>
          <p className="mt-0.5 text-[12.5px] text-slate-300">Two knowledge blocks — click to open.</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-md bg-white/[0.06] px-2 py-1 font-mono text-[10px] tracking-[0.08em] text-slate-300 uppercase">
          <i className="size-1.5 rounded-full bg-emerald-400 motion-safe:animate-pulse" />
          Capturing
        </span>
      </div>

      <div className="space-y-2 px-4 pb-4 pt-16 md:hidden">
        {MAP_NODES.map((id) => {
          const node = pulseNode(id, workerNames);
          return (
            <button
              key={id}
              type="button"
              onClick={() => onSelect(id)}
              className={cn(
                "flex min-h-11 w-full flex-col rounded-xl border bg-card px-3 py-3 text-left",
                mapFocus === id ? "border-primary" : "border-white/10",
              )}
            >
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-slate-400">{node.kicker}</span>
              <span className="mt-0.5 text-[15px] font-semibold text-foreground">{node.name}</span>
              <span className="mt-1 text-[13px] leading-relaxed text-slate-300">{node.summary}</span>
            </button>
          );
        })}
      </div>

      <div ref={wrapRef} className="relative hidden min-h-[500px] flex-1 md:block">
        <canvas ref={canvasRef} className="block h-full w-full" aria-label="Live knowledge map. Click a block to open it." />
        {hover && (
          <div
            role="tooltip"
            className={cn(
              "pointer-events-none absolute z-20 min-w-[210px] max-w-[280px] -translate-x-1/2 rounded-xl border border-white/15 bg-popover px-3.5 py-3 shadow-lg",
              hover.placement === "above" ? "-translate-y-full" : "translate-y-0",
            )}
            style={{ left: hover.x, top: hover.y }}
          >
            <p className="text-[14px] font-semibold text-foreground" style={{ fontFamily: "var(--font-display)" }}>{hover.name}</p>
            {hover.lines.map(([label, value]) => (
              <p key={label} className="mt-1 flex justify-between gap-3 text-[12.5px] text-slate-400">
                <span>{label}</span>
                <span className="font-semibold text-foreground">{value}</span>
              </p>
            ))}
            <p className="mt-2 text-[12px] font-semibold text-primary">{hover.cta}</p>
          </div>
        )}
        <div className="pointer-events-none absolute bottom-4 left-5 flex flex-wrap gap-3.5 text-[12px] text-slate-400">
          {AREAS.map((a) => (
            <span key={a.id} className="inline-flex items-center gap-1.5">
              <i className="size-2 rounded-full" style={{ background: a.col }} />
              {a.name}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function hexA(hex: string, alpha: number) {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

function ctrl(a: Pt, b: Pt, bend: number): Pt {
  return {
    x: (a.x + b.x) / 2 - (b.y - a.y) * bend,
    y: (a.y + b.y) / 2 + (b.x - a.x) * bend,
  };
}

function qp(a: Pt, c: Pt, b: Pt, t: number): Pt {
  const u = 1 - t;
  return {
    x: u * u * a.x + 2 * u * t * c.x + t * t * b.x,
    y: u * u * a.y + 2 * u * t * c.y + t * t * b.y,
  };
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
