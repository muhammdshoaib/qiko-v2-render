"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Search } from "lucide-react";
import { cn } from "@qiko/ui";
import { CockpitChatPanel } from "@/components/cockpit/chat-panel";
import { askCompanyBrain } from "./brain-ask";
import type { PulseNav } from "./route";

function isMac() {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
}

export function useAskBrainShortcut(onToggle: () => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onToggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onToggle]);
}

export function AskBrainTrigger({
  open,
  onToggle,
}: {
  open: boolean;
  onToggle: () => void;
}) {
  const shortcut = isMac() ? "⌘K" : "Ctrl K";
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls="company-brain-chat"
      aria-keyshortcuts={isMac() ? "Meta+K" : "Control+K"}
      className={cn(
        "flex h-9 min-w-0 flex-1 items-center gap-2 rounded-[10px] bg-white/[0.06] px-3 text-left text-[13px] sm:max-w-[380px]",
        open ? "text-white ring-1 ring-indigo-400/40" : "text-slate-500",
      )}
    >
      <Search className="size-3.5 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1 truncate">Ask your company brain</span>
      <kbd className="ml-auto hidden rounded-[5px] border border-white/10 bg-card px-1.5 py-0.5 font-mono text-[10px] text-slate-400 sm:inline">
        {shortcut}
      </kbd>
    </button>
  );
}

export function AskBrainChat({
  onClose,
  onNav,
}: {
  onClose: () => void;
  onNav: (next: Partial<PulseNav>) => void;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;
  return createPortal(
    <div id="company-brain-chat">
      <CockpitChatPanel
        workerName="Company brain"
        onClose={onClose}
        onAsk={(question) => askCompanyBrain(question, onNav)}
        emptyPrompt="Ask about Investors, Properties, Lombe House intent, or portfolio insights. Answers stay inside Pulse — nothing is sent outbound."
        placeholder="Ask your company brain..."
        inputHint="Labelled sample · Enter to send · does not contact anyone"
        errorText="Pulse could not answer from the labelled sample. Try Investors, Properties, or Lombe House."
        insetClassName="top-16 lg:top-[6.75rem]"
      />
    </div>,
    document.body,
  );
}
