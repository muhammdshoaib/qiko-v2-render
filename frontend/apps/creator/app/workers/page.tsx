"use client";

import Link from "next/link";
import { cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";

const KNOWLEDGE_BLOCKS = [
  {
    id: "investor-concierge",
    href: "/knowledge/investors",
    initials: "IC",
    name: "Investor Concierge",
    status: "Growing",
    value: "£18.4k",
    conversations: "214",
    toCrm: "23",
    agentNames: "Intent Signal Agent",
  },
  {
    id: "portfolio-reporter",
    href: "/knowledge/portfolio-reporter",
    initials: "PR",
    name: "Portfolio Reporter",
    status: "Established",
    value: "£12.1k",
    conversations: "96",
    toCrm: "0",
    agentNames: "Portfolio Insights",
  },
];

export default function KnowledgePage() {
  return (
    <AppShell title="Knowledge">
      <div className="relative flex flex-col gap-3 border-b border-white/[0.06] bg-[#070a12]/80 px-4 py-5 backdrop-blur-xl sm:flex-row sm:items-start sm:justify-between sm:px-6 sm:py-6">
        <div>
          <h1 className="mb-1 text-[28px] font-bold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>
            Knowledge
          </h1>
          <p className="max-w-[52ch] text-sm text-slate-400">
            Each knowledge block is one worker.
          </p>
        </div>
      </div>

      <div className="p-4 sm:p-6 lg:p-8">
        <div className="mx-auto max-w-6xl">
          <section aria-label="Knowledge blocks">
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
              {KNOWLEDGE_BLOCKS.map((block) => (
                <Link
                  key={block.id}
                  href={block.href}
                  className={cn(
                    "group flex min-h-[220px] flex-col rounded-2xl border border-white/[0.08] bg-[#0b0f18] p-5",
                    "transition-colors hover:border-white/[0.14] hover:bg-white/[0.03]",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className="grid size-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-[13px] font-extrabold text-white shadow-[0_8px_24px_-10px_rgba(79,70,229,0.8)]"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {block.initials}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h2 className="text-[17px] font-semibold text-white group-hover:text-cyan-200">{block.name}</h2>
                          <p className="mt-0.5 text-[12.5px] text-slate-500">
                            Knowledge block · {block.agentNames}
                          </p>
                        </div>
                        <span className="inline-flex items-center rounded-md bg-emerald-400/10 px-2 py-0.5 font-mono text-[10px] font-medium tracking-[0.04em] text-emerald-400">
                          {block.status}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-5 grid grid-cols-3 gap-2 border-y border-white/[0.06] py-4">
                    {[
                      [block.value, "Value this month"],
                      [block.conversations, "Conversations"],
                      [block.toCrm, "To CRM"],
                    ].map(([value, label]) => (
                      <div key={label} className="min-w-0">
                        <b className="block text-[18px] font-extrabold tracking-[-0.02em] text-white" style={{ fontFamily: "var(--font-display)" }}>
                          {value}
                        </b>
                        <span className="mt-0.5 block text-[11px] text-slate-500">{label}</span>
                      </div>
                    ))}
                  </div>

                  <p className="mt-auto pt-4 text-[12.5px] leading-relaxed text-slate-400">
                    {block.agentNames}
                  </p>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
