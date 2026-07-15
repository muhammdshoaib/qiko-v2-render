"use client";

// Shared cockpit chat side panel -- one component so every IDG worker cockpit (Sales Intelligence,
// Pre-Sales, ...) has an identical chat header, status line, empty state, message list, typing
// indicator, input styling and error handling. Only the per-worker context wording (empty-state
// prompt, input hint, placeholder, error copy) and the async ask() call are passed in as props, so
// the structure/spacing/typography can never drift between cockpits.
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { MessageSquare, Sparkles, X } from "lucide-react";
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
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: (question: string) => onAsk(question),
    onMutate: (question: string) => setMessages((m) => [...m, { role: "user", text: question }]),
    onSuccess: (reply) => setMessages((m) => [...m, { role: "assistant", text: reply }]),
    onError: () => setMessages((m) => [...m, { role: "assistant", text: errorText }]),
  });

  return (
    <>
      {/* Dim backdrop on mobile/tablet where the chat is an overlay drawer, not a fixed column. */}
      <div onClick={onClose} className="fixed inset-0 top-14 z-30 bg-black/50 lg:hidden" aria-hidden="true" />
      <aside
        className={cn(
          "z-40 flex w-[300px] shrink-0 flex-col border-l border-white/[0.06] bg-[#05070d]",
          // < lg: overlay drawer anchored under the header on the right.
          "fixed bottom-0 right-0 top-14 max-w-[86vw]",
          // lg+: revert to the inline side column.
          "lg:static lg:max-w-none",
        )}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3.5">
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

        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
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
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); const q = text.trim(); if (q && ready && !send.isPending) { send.mutate(q); setText(""); } }}
          className="border-t border-white/[0.06] p-3"
        >
          <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5 transition-colors focus-within:border-indigo-500/60 focus-within:ring-2 focus-within:ring-indigo-500">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={ready ? placeholder : (notReadyPlaceholder ?? placeholder)}
              aria-label="Chat message"
              disabled={!ready || send.isPending}
              className="w-full bg-transparent text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
            />
            <p className="mt-2 text-[10px] text-slate-600">{inputHint}</p>
          </div>
        </form>
      </aside>
    </>
  );
}
