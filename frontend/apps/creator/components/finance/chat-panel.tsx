"use client";

// "Ask Analyst" chat surface -- posts to POST /finance/{agentId}/chat and renders grounded answers.
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { MessageSquare, SendHorizonal, Sparkles } from "lucide-react";
import { cn } from "@qiko/ui";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { financeChat } from "@/lib/api";

const SUGGESTED = [
  "Which property has the highest net profit?",
  "Show me my biggest vendor by spend.",
  "Which properties are at highest risk?",
  "What are my largest expense categories?",
];

export function FinanceChatPanel({ agentId, workerName }: { agentId: string; workerName: string }) {
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: (message: string) => financeChat(agentId, message),
    onMutate: (message) => setMessages((m) => [...m, { role: "user", text: message }]),
    onSuccess: (reply) => setMessages((m) => [...m, { role: "assistant", text: reply.reply }]),
    onError: (err) => setMessages((m) => [...m, { role: "assistant", text: `Sorry — I couldn't answer that. (${(err as Error).message})` }]),
  });

  function submit(value: string) {
    const q = value.trim();
    if (!q || send.isPending) return;
    send.mutate(q);
    setText("");
  }

  return (
    <section className="flex h-full flex-col overflow-hidden rounded-2xl border border-white/[0.08]" style={{ background: "oklch(0.15 0.02 250)" }}>
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-white/[0.06] px-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-300"><MessageSquare className="h-4 w-4" /></span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white/90">Financial Chat</p>
          <p className="text-[11px] text-white/35">Grounded in {workerName}&apos;s uploaded workbooks</p>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-400"><Sparkles className="h-6 w-6" /></span>
            <p className="text-sm font-semibold text-white">Ask about your portfolio</p>
            <p className="mt-1.5 max-w-[280px] text-[12px] leading-relaxed text-white/50">
              Ask about property performance, vendor costs, profitability, arrears, or risk.
            </p>
            <div className="mt-4 flex max-w-md flex-wrap justify-center gap-2">
              {SUGGESTED.map((s) => (
                <button key={s} type="button" onClick={() => submit(s)}
                  className="rounded-lg border border-white/[0.1] bg-white/[0.03] px-2.5 py-1.5 text-[11px] text-white/70 transition-colors hover:bg-white/[0.06] hover:text-white">
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <ChatBubble role={m.role} text={m.text} />
            </div>
          ))
        )}
        {send.isPending && <div className="flex justify-start"><TypingIndicator /></div>}
      </div>

      <form onSubmit={(e) => { e.preventDefault(); submit(text); }} className="border-t border-white/[0.06] p-3">
        <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
          <input value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Ask about property performance, vendor costs, profitability…" aria-label="Ask the financial analyst"
            className="flex-1 bg-transparent text-[13px] text-white placeholder:text-white/40 focus:outline-none" />
          <button type="submit" disabled={send.isPending || !text.trim()} aria-label="Send message"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500 text-white transition-colors hover:bg-indigo-400 disabled:opacity-40">
            <SendHorizonal className="h-4 w-4" />
          </button>
        </div>
      </form>
    </section>
  );
}
