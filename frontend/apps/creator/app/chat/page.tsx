"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SendHorizonal } from "lucide-react";
import { Button, Input, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { ask, listAgents } from "@/lib/api";

type Msg = { role: string; text: string };

export default function ChatPage() {
  const [conversationId] = useState(() => `conv-${Date.now()}`);
  const workers = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const readyWorkers = (workers.data ?? []).filter((worker) => worker.status === "ready");
  const [agentId, setAgentId] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!readyWorkers.some((worker) => worker.id === agentId)) {
      setAgentId(readyWorkers[0]?.id ?? "");
    }
  }, [agentId, readyWorkers]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input || !agentId) return;
    const q = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const reply = await ask(conversationId, q, agentId);
      setMessages((m) => [...m, reply]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Sorry, something went wrong. Please try again." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Chat">
      <div className="mx-auto flex h-[calc(100vh-7rem)] max-w-2xl flex-col">
        <label className="mb-4 block text-sm font-medium">
          Worker
          <select
            className="mt-1 min-h-11 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={agentId}
            onChange={(event) => setAgentId(event.target.value)}
            disabled={workers.isLoading || busy}
          >
            {readyWorkers.length === 0 && <option value="">No ready workers available</option>}
            {readyWorkers.map((worker) => <option key={worker.id} value={worker.id}>{worker.name}</option>)}
          </select>
        </label>
        {workers.isError && (
          <p className="mb-4 text-sm text-destructive">
            Couldn&apos;t load workers. <button className="underline" onClick={() => workers.refetch()}>Retry</button>
          </p>
        )}
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
          <Input placeholder="Message your worker…" value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} aria-label="Message your worker" />
          <Button type="submit" size="icon" disabled={busy || !agentId}><SendHorizonal className="size-4" /></Button>
        </form>
      </div>
    </AppShell>
  );
}
