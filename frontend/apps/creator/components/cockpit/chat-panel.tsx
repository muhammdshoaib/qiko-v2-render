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

// Desktop width bounds for the resizable panel. The minimum is the width the panel had while it
// was still an inline column, below which the composer and a citation line stop being readable;
// the maximum leaves the content it floats over usable rather than fully covered.
const MIN_WIDTH = 300;
const MAX_WIDTH = 720;
const DEFAULT_WIDTH = 420;
const WIDTH_STORAGE_KEY = "qiko.cockpitChatWidth";
// One arrow keypress on the handle. Matches the 24px spacing step the cockpit already uses, and is
// coarse enough that resizing by keyboard does not take fifty presses.
const KEYBOARD_STEP = 24;

function clampWidth(width: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(width)));
}

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
  loadHistory, historyKey, insetClassName = "top-14",
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
  /** Viewport offset for the overlay. Cockpits sit under the h-14 top bar; Pulse sits under Intelligence chrome. */
  insetClassName?: string;
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

  // Desktop width, restored after mount rather than in a lazy initialiser: localStorage does not
  // exist while this renders on the server, and reading it during the first client render would
  // make that render disagree with the server's.
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [resizing, setResizing] = useState(false);
  useEffect(() => {
    const stored = Number(window.localStorage.getItem(WIDTH_STORAGE_KEY));
    if (Number.isFinite(stored) && stored > 0) setWidth(clampWidth(stored));
  }, []);

  function persistWidth(next: number) {
    setWidth(next);
    try {
      window.localStorage.setItem(WIDTH_STORAGE_KEY, String(next));
    } catch {
      // A blocked or full localStorage must not break resizing; the width just won't be remembered.
    }
  }

  // Pointer events rather than mouse events, and setPointerCapture, so a fast drag that leaves the
  // 3px handle (or the window) keeps resizing and still ends on release.
  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    setResizing(true);

    const onMove = (move: PointerEvent) => {
      // Anchored right: dragging left (a smaller clientX) makes the panel wider.
      persistWidth(clampWidth(startWidth + (startX - move.clientX)));
    };
    const onUp = () => {
      setResizing(false);
      handle.releasePointerCapture(event.pointerId);
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onUp);
      handle.removeEventListener("pointercancel", onUp);
    };
    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onUp);
    handle.addEventListener("pointercancel", onUp);
  }

  function resizeByKey(event: React.KeyboardEvent<HTMLDivElement>) {
    const step = event.key === "ArrowLeft" ? KEYBOARD_STEP
      : event.key === "ArrowRight" ? -KEYBOARD_STEP
        : 0;
    if (!step) return;
    event.preventDefault();
    persistWidth(clampWidth(width + step));
  }

  return (
    <>
      {/* Dim backdrop only below lg, where the chat is a modal drawer over the whole view. At lg+
          the panel floats above the content without dimming it, so a reviewer can keep reading the
          tender (and copy from it) while asking questions. */}
      <div onClick={onClose} className={cn("fixed inset-0 z-30 bg-black/50 lg:hidden", insetClassName)} aria-hidden="true" />
      <aside
        // The width lives in a custom property, not an inline width: below lg the panel is a touch
        // drawer whose width is the class-driven one, and only the lg+ class consumes the variable.
        // An inline width would win at every breakpoint and there is no media query in style={}.
        style={{ "--cockpit-chat-width": `${width}px` } as React.CSSProperties}
        className={cn(
          "z-40 flex min-h-0 w-[300px] flex-col border-l border-white/[0.06] bg-[#05070d]",
          // Overlay anchored under the header on the right, at every width. It is deliberately NOT
          // an inline flex column at lg+ any more: as a column it took permanent horizontal space
          // and squeezed <main> into a narrow strip, which read as a thin sidebar rather than a
          // chat (client feedback, 2026-09-16). Floating it leaves the content full-width.
          "fixed bottom-0 right-0 max-w-[86vw] shadow-2xl shadow-black/50",
          insetClassName,
          // Resizable on desktop, where there is a pointer to drag the edge with.
          "lg:w-[var(--cockpit-chat-width)] lg:max-w-none",
          // A drag that crosses the transcript would otherwise select its text.
          resizing && "select-none",
        )}
      >
        {/* Drag handle on the left edge (the panel is anchored right). Desktop only: below lg the
            panel is a full-height touch drawer capped at 86vw, where a 3px edge is not a gesture
            anyone can hit. role=separator with aria-orientation/valuenow is what makes it a
            resize control to a screen reader rather than a decorative strip. */}
        <div
          onPointerDown={startResize}
          onKeyDown={resizeByKey}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize chat panel"
          aria-valuenow={width}
          aria-valuemin={MIN_WIDTH}
          aria-valuemax={MAX_WIDTH}
          tabIndex={0}
          className={cn(
            "absolute inset-y-0 left-0 hidden w-1.5 -translate-x-1/2 cursor-col-resize lg:block",
            "after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:bg-transparent",
            "hover:after:bg-indigo-400/60 focus-visible:outline-none focus-visible:after:bg-indigo-400",
            resizing && "after:bg-indigo-400",
          )}
        />
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
