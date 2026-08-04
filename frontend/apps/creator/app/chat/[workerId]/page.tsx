"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Loader2, SendHorizonal, ShieldAlert } from "lucide-react";
import { Button, Input, Logo, cn } from "@qiko/ui";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { publicChatById, publicWorkerDetail, type PublicWorker } from "@/lib/api";

type Msg = { role: string; text: string };

// Public guest chat by worker ID (QIK-334). No auth, no tenant: the worker is resolved server-side
// and must be `ready` (mirrors V1 /chat/:workerId). Middleware marks /chat/<id> public.
export default function PublicChatByIdPage() {
  const { workerId } = useParams<{ workerId: string }>();
  const [worker, setWorker] = useState<PublicWorker | null>(null);
  const [loading, setLoading] = useState(true);
  const [notAvailable, setNotAvailable] = useState(false);
  const [email, setEmail] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true); setNotAvailable(false);
    publicWorkerDetail(workerId)
      .then((w) => { if (active) setWorker(w); })
      .catch(() => { if (active) setNotAvailable(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [workerId]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const reply = await publicChatById(workerId, q, email.trim() || undefined);
      setMessages((m) => [...m, reply]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Sorry, I couldn't respond just now. Please try again." }]);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-dvh items-center justify-center bg-background" role="status">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  if (notAvailable || !worker) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-3 bg-background px-6 text-center">
        <ShieldAlert className="size-8 text-amber-400" />
        <h1 className="text-lg font-semibold text-foreground">This chat isn&apos;t available</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          The link may be invalid, or this worker isn&apos;t published for public chat yet.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-dvh max-w-2xl flex-col bg-background">
      <header className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Logo className="text-sm" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold capitalize text-foreground">{worker.name}</p>
          <p className="text-xs text-muted-foreground">AI assistant</p>
        </div>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="py-10 text-center text-sm text-muted-foreground">
            <p>Hi! I&apos;m {worker.name}. Ask me anything.</p>
            <div className="mx-auto mt-4 max-w-xs">
              <Input type="email" inputMode="email" aria-label="Your email (optional)"
                placeholder="Your email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} />
              <p className="mt-1 text-xs text-muted-foreground">Leave your email so we can follow up.</p>
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <ChatBubble role={m.role} text={m.text} />
          </div>
        ))}
        {busy && <div className="flex justify-start"><TypingIndicator /></div>}
      </div>

      <form onSubmit={send} className="flex gap-2 border-t border-border p-3">
        <Input placeholder="Type a message..." aria-label="Message" value={input}
          onChange={(e) => setInput(e.target.value)} />
        <Button type="submit" size="icon" disabled={busy || !input.trim()} aria-label="Send">
          <SendHorizonal className="size-4" />
        </Button>
      </form>
    </div>
  );
}
