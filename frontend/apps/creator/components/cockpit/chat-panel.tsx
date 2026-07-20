"use client";

// Shared cockpit chat side panel -- one component so every IDG worker cockpit (Sales Intelligence,
// Pre-Sales, ...) has an identical chat header, status line, empty state, message list, typing
// indicator, input styling and error handling. Only the per-worker context wording (empty-state
// prompt, input hint, placeholder, error copy) and the async ask() call are passed in as props, so
// the structure/spacing/typography can never drift between cockpits.
import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { MessageSquare, SendHorizonal, Sparkles, X } from "lucide-react";
import { cn } from "@qiko/ui";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";

type ChatMessage = { role: string; text: string };

function ChatEmptyState({ title, prompt }: { title: string; prompt: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <span className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-400">
        <Sparkles className="size-6" />
      </span>
      <p className="text-sm font-semibold text-white">{title}</p>
      <p className="mt-1.5 max-w-[220px] text-[12px] leading-relaxed text-slate-500">{prompt}</p>
    </div>
  );
}

export function CockpitChatPanel({
  workerName, onClose, onAsk, ready = true,
  emptyPrompt, notReadyTitle, notReadyPrompt,
  placeholder, notReadyPlaceholder, inputHint, errorText,
  loadHistory, historyKey,
}: {
  workerName: string;
  onClose: () => void;
  /** Resolve to the assistant's reply text. Rejects surface `errorText` in the transcript. */
  onAsk: (question: string) => Promise<string>;
  /** When false, the panel shows the not-ready empty state and disables the input. */
  ready?: boolean;
  emptyPrompt: string;
  notReadyTitle?: string;
  notReadyPrompt?: string;
  placeholder: string;
  notReadyPlaceholder?: string;
  inputHint: string;
  errorText: string;
  /**
   * Optional: fetch the persisted conversation to seed the transcript on mount and whenever
   * `historyKey` changes (e.g. switching to a different tender). Off by default, so cockpits that
   * don't persist chat behave exactly as before (in-memory only).
   */
  loadHistory?: () => Promise<ChatMessage[]>;
  /** Identifies the conversation being shown; changing it reloads history for the new context. */
  historyKey?: string | null;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");

  // Seed/reload the transcript from persisted history when the active conversation changes, so
  // reopening the chat or refreshing (or switching tenders) restores the prior exchange. Guarded
  // by a per-run flag so a slow fetch for a previous key can't overwrite a newer one.
  useEffect(() => {
    if (!loadHistory || !historyKey) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setMessages([]);
    loadHistory()
      .then((prior) => { if (!cancelled) setMessages(prior); })
      .catch(() => { if (!cancelled) setMessages([]); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyKey]);
  const send = useMutation({
    mutationFn: (question: string) => onAsk(question),
    onMutate: (question: string) => setMessages((m) => [...m, { role: "user", text: question }]),
    onSuccess: (reply) => setMessages((m) => [...m, { role: "assistant", text: reply }]),
    onError: () => setMessages((m) => [...m, { role: "assistant", text: errorText }]),
  });

  // Keep the newest message (and the typing indicator) in view so the latest reply and the composer
  // are both visible after each send/receive.
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, send.isPending]);

  const canSend = ready && !send.isPending && text.trim().length > 0;

  return (
    <>
      {/* Dim backdrop on mobile/tablet where the chat is an overlay drawer, not a fixed column. */}
      <div onClick={onClose} className="fixed inset-0 top-14 z-30 bg-black/50 lg:hidden" aria-hidden="true" />
      <aside
        className={cn(
          "z-40 flex min-h-0 w-[300px] shrink-0 flex-col border-l border-white/[0.06] bg-[#05070d]",
          // < lg: overlay drawer anchored under the header on the right.
          "fixed bottom-0 right-0 top-14 max-w-[86vw]",
          // lg+: revert to the inline side column.
          "lg:static lg:max-w-none",
        )}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-4 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400">
              <MessageSquare className="size-4" />
            </span>
            <div>
              <p className="text-[13px] font-semibold text-white">Chat with {workerName}</p>
              <p className="flex items-center gap-1 text-[11px] text-slate-500">
                <span className="size-1.5 rounded-full bg-emerald-400" /> AI assistant &middot; online
              </p>
            </div>
          </div>
          <button onClick={onClose} aria-label="Close chat" className="rounded-md text-slate-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60">
            <X className="size-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {!ready ? (
            <ChatEmptyState title={notReadyTitle ?? "Start a conversation"} prompt={notReadyPrompt ?? emptyPrompt} />
          ) : messages.length === 0 ? (
            <ChatEmptyState title="Start a conversation" prompt={emptyPrompt} />
          ) : (
            messages.map((m, i) => (
              <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <ChatBubble role={m.role} text={m.text} />
              </div>
            ))
          )}
          {send.isPending && <div className="flex justify-start"><TypingIndicator /></div>}
          {/* Scroll anchor: the effect scrolls this into view on every send/receive. */}
          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); const q = text.trim(); if (q && ready && !send.isPending) { send.mutate(q); setText(""); } }}
          className="shrink-0 border-t border-white/[0.06] p-3"
        >
          {/* Claude-style composer: a rounded input row with a visible send button on the right. */}
          <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2 transition-colors focus-within:border-indigo-500/60 focus-within:ring-2 focus-within:ring-indigo-500">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={ready ? placeholder : (notReadyPlaceholder ?? placeholder)}
              aria-label="Chat message"
              disabled={!ready || send.isPending}
              className="min-w-0 flex-1 bg-transparent py-1 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!canSend}
              aria-label="Send message"
              className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-indigo-500 text-white transition-colors hover:bg-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-slate-500"
            >
              <SendHorizonal className="size-4" />
            </button>
          </div>
          <p className="mt-2 px-1 text-[10px] text-slate-600">{inputHint}</p>
        </form>
      </aside>
    </>
  );
}
