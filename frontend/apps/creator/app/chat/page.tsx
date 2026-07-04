"use client";

import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { Button, Input, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { ask } from "@/lib/api";

type Msg = { role: string; text: string };

export default function ChatPage() {
  const [conversationId] = useState(() => `conv-${Date.now()}`);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input) return;
    const q = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const reply = await ask(conversationId, q);
      setMessages((m) => [...m, reply]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Chat">
      <div className="mx-auto flex h-[calc(100vh-7rem)] max-w-2xl flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto pb-4">
          {messages.length === 0 && (
            <p className="py-16 text-center text-sm text-muted-foreground">Ask your worker anything.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cn(
                "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm",
                m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground",
              )}>
                {m.text}
              </div>
            </div>
          ))}
          {busy && <p className="text-sm text-muted-foreground">Thinking…</p>}
        </div>
        <form onSubmit={send} className="flex gap-2 border-t border-border pt-4">
          <Input placeholder="Message your worker…" value={input} onChange={(e) => setInput(e.target.value)} />
          <Button type="submit" size="icon" disabled={busy}><SendHorizonal className="size-4" /></Button>
        </form>
      </div>
    </AppShell>
  );
}
