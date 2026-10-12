"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, cn } from "@qiko/ui";
import { toast } from "sonner";
import { HonestyBadge } from "./honesty-badge";
import {
  SENSITIVE_QUESTION,
  USERS,
  authorize,
  channelLabel,
  useBrain,
  type DemoUserId,
} from "@/lib/brain/store";

export function ChannelSurfaces() {
  const params = useSearchParams();
  const router = useRouter();
  const surface = params.get("surface") === "slack" ? "slack" : "claude";

  const setSurface = (next: "claude" | "slack") => {
    const query = new URLSearchParams(params.toString());
    query.set("tab", "channels");
    query.set("surface", next);
    router.replace(`/studio/intelligence?${query.toString()}`, { scroll: false });
  };

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-white" style={{ fontFamily: "var(--font-display)" }}>Familiar tools</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-400">
          The same Property Insights and Intelligence workers. These conversations are labelled walkthroughs — not a signed-in Claude account or a live Slack workspace.
        </p>
      </div>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Surface">
        {([
          { id: "claude" as const, label: "Claude" },
          { id: "slack" as const, label: "Slack" },
        ]).map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={surface === item.id}
            onClick={() => setSurface(item.id)}
            className={cn(
              "min-h-11 rounded-lg px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
              surface === item.id ? "bg-white/[0.08] text-white" : "text-slate-400 hover:text-white",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      {surface === "claude" ? <ClaudePanel /> : <SlackPanel />}
    </div>
  );
}

function ClaudePanel() {
  const brain = useBrain();
  const access = authorize("maya", "claude", brain.config);
  const messages = brain.messages.filter((item) => item.surface === "claude");

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-white">Simulated Claude</h3>
            <p className="mt-1 text-[12px] text-slate-500">Signed-in operator: Maya Chen. Not an Anthropic session.</p>
          </div>
          <HonestyBadge kind="illustrative" />
        </div>
        <Gate access={access} label="Claude" />
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <Button type="button" size="sm" onClick={() => toast.message(brain.askClaudeInsight())}>
            Ask for a portfolio insight
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => toast.message(brain.askClaudeFollowUp())}>
            Request a Lombe House follow-up
          </Button>
        </div>
        <Thread messages={messages} empty="Ask one of the questions above. The worker answers from knowledge it already has." />
        {brain.approval === "awaiting" && (
          <article className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/[0.06] p-4">
            <h4 className="text-sm font-semibold text-white">Recommended action</h4>
            <p className="mt-2 text-[13px] text-slate-300">Flag Lombe House / Derby for a leadership review. No investor email will be sent.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button type="button" size="sm" onClick={() => toast.message(brain.approveFollowUp())}>
                Approve review
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => toast.message(brain.holdFollowUp())}>
                Hold
              </Button>
            </div>
          </article>
        )}
        {brain.approval === "approved" && (
          <p className="mt-4 text-[13px] text-emerald-300">Review recorded on the company record. Nothing was sent outbound.</p>
        )}
        {brain.approval === "held" && (
          <p className="mt-4 text-[13px] text-slate-400">Review held. Nothing was written to the company record or sent outbound.</p>
        )}
      </section>
      <aside className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4 text-[13px] text-slate-400">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">What this writes</p>
        <p className="mt-2">Insight questions are reads. Approving the Lombe House review writes a completed decision to Creator. A draft does not.</p>
      </aside>
    </div>
  );
}

function SlackPanel() {
  const brain = useBrain();
  const params = useSearchParams();
  const router = useRouter();
  const [userId, setUserId] = useState<DemoUserId>("maya");
  const slack: "ops" | "leadership" = params.get("channel") === "leadership" ? "leadership" : "ops";
  const access = authorize(userId, slack, brain.config);
  const messages = brain.messages.filter((item) => item.surface === slack);

  const setSlack = (next: "ops" | "leadership") => {
    const query = new URLSearchParams(params.toString());
    query.set("tab", "channels");
    query.set("surface", "slack");
    query.set("channel", next);
    router.replace(`/studio/intelligence?${query.toString()}`, { scroll: false });
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
      <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-white">Simulated Slack · {channelLabel(slack, brain.config)}</h3>
            <p className="mt-1 text-[12px] text-slate-500">Not a live workspace. Channel and user both gate the answer.</p>
          </div>
          <HonestyBadge kind="illustrative" />
        </div>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <fieldset>
            <legend className="text-[11px] uppercase tracking-wider text-slate-500">Acting as</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {Object.values(USERS).map((user) => (
                <button
                  key={user.id}
                  type="button"
                  aria-pressed={userId === user.id}
                  onClick={() => setUserId(user.id)}
                  className={cn(
                    "min-h-11 rounded-lg border px-3 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                    userId === user.id ? "border-white/25 bg-white/10 text-white" : "border-white/[0.08] text-slate-400",
                  )}
                >
                  <span className="block">{user.name}</span>
                  <span className="block text-[11px] text-slate-500">{user.role} · sensitive {user.sensitive ? "yes" : "no"}</span>
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="text-[11px] uppercase tracking-wider text-slate-500">Channel</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {(["ops", "leadership"] as const).map((id) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={slack === id}
                  onClick={() => setSlack(id)}
                  className={cn(
                    "min-h-11 rounded-lg border px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60",
                    slack === id ? "border-white/25 bg-white/10 text-white" : "border-white/[0.08] text-slate-400",
                  )}
                >
                  {channelLabel(id, brain.config)}
                </button>
              ))}
            </div>
          </fieldset>
        </div>
        <Gate access={access} label={channelLabel(slack, brain.config)} />
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <Button type="button" size="sm" onClick={() => toast.message(brain.askSlack(slack, userId, "ops"))}>
            Ask next steps
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => toast.message(brain.askSlack(slack, userId, "sensitive"))}>
            Ask the portfolio figure
          </Button>
        </div>
        <p className="mt-2 text-[12px] text-slate-500">Same restricted question: “{SENSITIVE_QUESTION}”</p>
        <Thread messages={messages} empty={`Ask in ${channelLabel(slack, brain.config)}. Operational updates are allowed. Client portfolio figures follow the walls below.`} />
      </section>
      <aside className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4 text-[13px] text-slate-400">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Walls</p>
        <ul className="mt-2 space-y-2">
          <li>#{brain.config.opsName}: operational only{brain.config.opsAllowsSensitive ? " (sensitive currently on)" : ""}.</li>
          <li>#{brain.config.leadershipName}: sensitive figures for authorised users.</li>
          <li>Owen remains restricted in both channels.</li>
        </ul>
        <p className="mt-3 text-[12px] text-slate-500">Rename channels in Settings. Every allow or block appears in the Creator feed.</p>
      </aside>
    </div>
  );
}

function Gate({ access, label }: { access: ReturnType<typeof authorize>; label: string }) {
  return (
    <p className={cn("mt-3 rounded-lg border px-3 py-2 text-[12px]", access.sensitive ? "border-emerald-500/20 text-emerald-300" : "border-amber-500/20 text-amber-200")}>
      {access.sensitive
        ? `${label} may include labelled sample client portfolio figures for this operator.`
        : access.reason}
    </p>
  );
}

function Thread({ messages, empty }: { messages: { id: string; role: "user" | "worker"; text: string; at: string }[]; empty: string }) {
  if (messages.length === 0) {
    return <p className="mt-4 rounded-xl border border-dashed border-white/10 px-3 py-8 text-center text-[13px] text-slate-500">{empty}</p>;
  }
  return (
    <ul className="mt-4 space-y-2" aria-live="polite">
      {messages.map((item) => (
        <li key={item.id} className={cn("rounded-xl px-3 py-2.5 text-[13px]", item.role === "user" ? "bg-white/[0.04] text-slate-200" : "border border-white/[0.06] text-slate-300")}>
          <p>{item.text}</p>
          <p className="mt-1 text-[11px] text-slate-500">{item.at}</p>
        </li>
      ))}
    </ul>
  );
}

export function ChannelSettings() {
  const brain = useBrain();
  return (
    <section className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-4">
      <h3 className="text-sm font-semibold text-white">Slack channel walls</h3>
      <p className="mt-1 text-[12px] text-slate-500">Names and restrictions are local to this demonstration.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-[13px] text-slate-400">
          Operational channel
          <input
            className="mt-1 w-full rounded-lg border border-white/10 bg-[#070a12] px-3 py-2 text-white"
            value={brain.config.opsName}
            onChange={(event) => brain.updateConfig({ opsName: event.target.value.replace(/^#/, "") || "ops" })}
          />
        </label>
        <label className="text-[13px] text-slate-400">
          Leadership channel
          <input
            className="mt-1 w-full rounded-lg border border-white/10 bg-[#070a12] px-3 py-2 text-white"
            value={brain.config.leadershipName}
            onChange={(event) => brain.updateConfig({ leadershipName: event.target.value.replace(/^#/, "") || "leadership" })}
          />
        </label>
      </div>
      <div className="mt-3 flex flex-col gap-2">
        <label className="flex min-h-11 items-center gap-2 text-[13px] text-slate-300">
          <input type="checkbox" checked={brain.config.opsAllowsSensitive} onChange={(event) => brain.updateConfig({ opsAllowsSensitive: event.target.checked })} />
          #{brain.config.opsName} may share sensitive figures
        </label>
        <label className="flex min-h-11 items-center gap-2 text-[13px] text-slate-300">
          <input type="checkbox" checked={brain.config.leadershipAllowsSensitive} onChange={(event) => brain.updateConfig({ leadershipAllowsSensitive: event.target.checked })} />
          #{brain.config.leadershipName} may share sensitive figures
        </label>
      </div>
      <Button type="button" size="sm" variant="outline" className="mt-4" onClick={() => { brain.resetDemo(); toast.message("Demonstration reset."); }}>
        Reset demonstration
      </Button>
    </section>
  );
}
