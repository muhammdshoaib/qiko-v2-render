"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Ban, BookOpen, Eye, Network, Shield, Sparkles, Wrench } from "lucide-react";
import { Button, cn } from "@qiko/ui";
import { toast } from "sonner";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { useBrain } from "@/lib/brain/store";
import type { ShowcaseWorker } from "@/lib/studio/showcase";

export function WorkerProfile({ worker }: { worker: ShowcaseWorker }) {
  const router = useRouter();
  const brain = useBrain();
  const pending = brain.ready && worker.slug === "intent-intelligence" && brain.approval === "awaiting";
  const recorded = brain.ready && worker.slug === "intent-intelligence" && brain.approval !== "awaiting";
  const insights = worker.insights.map((item) =>
    recorded && item.title.includes("Lombay")
      ? { ...item, status: "completed" as const, detail: "Leadership review is on the company record. No investor email was sent." }
      : item,
  );
  const actions = recorded
    ? [{
        title: brain.approval === "approved" ? "Lombay review recorded" : "Lombay review held",
        detail: brain.approval === "approved"
          ? "The cluster is on the company record. No outbound contact was sent."
          : "The recommendation stays open. Nothing was written or sent.",
        at: "Just now",
        status: "completed" as const,
        origin: "record" as const,
        originLabel: "Company intelligence",
      }, ...worker.actions]
    : worker.actions;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 px-4 py-6 sm:px-6 lg:px-12">
      <button
        type="button"
        onClick={() => router.push("/studio")}
        className="inline-flex min-h-11 items-center gap-1 text-sm text-slate-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
      >
        <ArrowLeft className="size-4" /> Back to Pulse
      </button>

      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{worker.role}</p>
          <h1 className="mt-1 text-2xl font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>{worker.name}</h1>
          <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-slate-400">{worker.purpose}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-emerald-400/[0.08] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-400/80">Active</span>
            <HonestyBadge kind="illustrative" />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {worker.liveHref && (
            <Button type="button" onClick={() => router.push(worker.liveHref!)}>Open live cockpit</Button>
          )}
          <Button type="button" variant="outline" onClick={() => router.push(`/studio?focus=${worker.slug}`)}>
            <Network className="size-4" /> See in Pulse
          </Button>
          <Button type="button" variant="outline" onClick={() => router.push("/studio/intelligence?tab=channels&surface=claude")}>
            Ask in Claude
          </Button>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Block icon={BookOpen} title="Responsibilities" items={worker.responsibilities} />
        <Block icon={Sparkles} title="Capabilities" items={worker.capabilities} />
        <PairBlock icon={Eye} title="Knowledge sources" rows={worker.sources} />
        <PairBlock icon={Wrench} title="Connected systems" rows={worker.systems} />
      </div>

      {pending && (
        <article className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.06] p-5">
          <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
            Recommended follow-up
          </h2>
          <p className="mt-2 text-[13px] text-slate-300">
            Flag Lombay House / Derby for a leadership review. This writes to company intelligence. No investor email will be sent.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" size="sm" onClick={() => toast.message(brain.approveFollowUp())}>Approve review</Button>
            <Button type="button" size="sm" variant="outline" onClick={() => toast.message(brain.holdFollowUp())}>Hold</Button>
          </div>
        </article>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <OutcomeBlock title="Recent insights" items={insights} />
        <OutcomeBlock title="Completed actions" items={actions} />
      </div>

      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
          <Shield className="size-4 text-amber-300" /> Permissions and approvals
        </h2>
        <ul className="mt-4 space-y-2">
          {worker.permissions.map((item) => (
            <li key={item.name} className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.04] px-3 py-2 text-sm">
              <span className="text-slate-200">{item.name}</span>
              <span className={cn(
                "rounded-full border px-2 py-0.5 text-[11px]",
                item.mode === "allowed" && "border-emerald-500/25 text-emerald-300",
                item.mode === "requires review" && "border-amber-500/25 text-amber-300",
                item.mode === "blocked" && "border-red-500/25 text-red-300",
              )}>
                {item.mode === "blocked" ? (
                  <span className="inline-flex items-center gap-1"><Ban className="size-3" /> {item.mode}</span>
                ) : item.mode}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.04] p-5">
        <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
          Contribution to company intelligence
        </h2>
        <p className="mt-2 text-[14px] leading-relaxed text-slate-300">{worker.intelligence}</p>
        <Link
          href={`/studio/intelligence?focus=${worker.slug}`}
          className="mt-4 inline-flex min-h-11 items-center gap-1 text-sm text-cyan-200 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
        >
          Explore the intelligence layer <ArrowLeft className="size-3.5 rotate-180" />
        </Link>
      </section>
    </div>
  );
}

function Block({ icon: Icon, title, items }: { icon: typeof BookOpen; title: string; items: string[] }) {
  return (
    <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
        <Icon className="size-4 text-slate-400" /> {title}
      </h2>
      <ul className="mt-3 space-y-2 text-[13px] text-slate-300">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </section>
  );
}

function PairBlock({ icon: Icon, title, rows }: { icon: typeof Eye; title: string; rows: { name: string; detail: string }[] }) {
  return (
    <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>
        <Icon className="size-4 text-slate-400" /> {title}
      </h2>
      <ul className="mt-3 space-y-3">
        {rows.map((row) => (
          <li key={row.name}>
            <p className="text-sm text-white">{row.name}</p>
            <p className="mt-0.5 text-[12px] text-slate-400">{row.detail}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function OutcomeBlock({ title, items }: { title: string; items: ShowcaseWorker["insights"] }) {
  return (
    <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <h2 className="text-[15px] font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>{title}</h2>
      <ul className="mt-3 space-y-3">
        {items.map((item) => (
          <li key={item.title} className="rounded-xl border border-white/[0.04] bg-white/[0.02] px-3 py-3">
            <p className="text-sm text-white">{item.title}</p>
            <p className="mt-1 text-[12px] text-slate-400">{item.detail}</p>
            <p className="mt-2 text-[11px] text-slate-500">{item.at}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
