"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { SendHorizonal } from "lucide-react";
import { Button, Input, Logo, cn } from "@qiko/ui";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { publicChat } from "@/lib/api";

type Msg = { role: string; text: string };

export default function EmbedChatPage() {
  const { tenant, worker } = useParams<{ tenant: string; worker: string }>();
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
      const reply = await publicChat(tenant, worker, q);
      setMessages((m) => [...m, reply]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Sorry, I'm not available right now." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Logo className="text-sm" />
        <span className="text-xs text-muted-foreground">AI assistant</span>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="py-10 text-center text-sm text-muted-foreground">Hi! Ask me anything.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <ChatBubble role={m.role} text={m.text} />
          </div>
        ))}
        {busy && <div className="flex justify-start"><TypingIndicator /></div>}
      </div>
      <form onSubmit={send} className="flex gap-2 border-t border-border p-3">
        <Input placeholder="Type a message…" value={input} onChange={(e) => setInput(e.target.value)} />
        <Button type="submit" size="icon" disabled={busy}><SendHorizonal className="size-4" /></Button>
      </form>
    </div>
  );
}
