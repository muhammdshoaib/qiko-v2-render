"use client";

/**
 * QIKO-1073: read-only support view of an intelligence worker's own chat and discrepancies,
 * opened from a Workers directory row. Mirrors the RowActivityDialog pattern (a drawer opened
 * from a row) rather than a new route, since this is a secondary, occasional action.
 */
import { useEffect, useRef, useState } from "react";
import { Badge, Button, Dialog } from "@qiko/ui";
import {
  getSupportConversationHistory, getSupportWorker, listSupportConversations,
  listSupportDiscrepancies, type SupportConversation, type SupportDiscrepancy,
  type SupportMessage,
} from "@/lib/api";

type Tab = "conversations" | "discrepancies";

export function WorkerSupportDialog({ open, agentId, workerName, onClose }: {
  open: boolean;
  agentId: string;
  workerName: string;
  onClose: () => void;
}) {
  const opener = useRef<HTMLElement | null>(null);
  const [tab, setTab] = useState<Tab>("conversations");
  const [conversations, setConversations] = useState<SupportConversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [history, setHistory] = useState<SupportMessage[]>([]);
  const [discrepancies, setDiscrepancies] = useState<SupportDiscrepancy[]>([]);
  // idle until the Discrepancies tab is actually selected: discrepancy summary/title/ref text is
  // real tenant content, exactly what QIW-1007's privacy rationale says this view should minimize
  // pulling into the browser (and each fetch also writes a SUPPORT_WORKER_VIEWED audit row), so it
  // must not load just because the dialog opened, unlike the worker check and the conversation
  // LIST metadata, which carry no message content.
  const [discrepanciesStatus, setDiscrepanciesStatus] = useState<"idle" | "loading" | "done">("idle");
  const [error, setError] = useState<string | null>(null);

  if (typeof document !== "undefined" && open && !opener.current) {
    opener.current = document.activeElement as HTMLElement;
  }
  if (!open) opener.current = null;

  useEffect(() => {
    if (!open) return;
    setError(null);
    setActiveConversation(null);
    setConversations([]);
    setDiscrepancies([]);
    setDiscrepanciesStatus("idle");
    // Sequenced rather than fired in parallel: if the worker itself is gone or refused, the list
    // call would 403/404 too, and independent .catch()es writing the same error state raced to
    // decide which message won. Confirming the worker first means only one error can ever be
    // shown, and the conversation list only loads once there is something to list.
    getSupportWorker(agentId)
      .then(() => {
        listSupportConversations(agentId).then(setConversations).catch(() => setError("Could not load conversations."));
      })
      .catch(() => setError("This worker no longer has a support view."));
  }, [open, agentId]);

  useEffect(() => {
    if (!activeConversation) { setHistory([]); return; }
    getSupportConversationHistory(agentId, activeConversation).then(setHistory).catch(() => setError("Could not load that conversation."));
  }, [agentId, activeConversation]);

  // Lazy, and only once per dialog-open: fires the first time the admin lands on the
  // Discrepancies tab, not on every switch back to it, and the "idle" reset above (keyed on
  // [open, agentId]) means reopening the dialog, or switching it to a different worker, fetches
  // fresh rather than reusing a previous worker's discrepancies.
  useEffect(() => {
    if (!open || tab !== "discrepancies" || discrepanciesStatus !== "idle") return;
    setDiscrepanciesStatus("loading");
    listSupportDiscrepancies(agentId)
      .then((body) => { setDiscrepancies(body.items); setDiscrepanciesStatus("done"); })
      .catch(() => { setError("Could not load discrepancies."); setDiscrepanciesStatus("done"); });
  }, [open, tab, agentId, discrepanciesStatus]);

  return (
    <Dialog open={open} onClose={onClose} opener={opener.current}
      labelledBy="worker-support-title" className="max-w-2xl">
      <div className="space-y-4">
        <div>
          <h2 id="worker-support-title" className="text-lg font-semibold">Support view: {workerName}</h2>
          <p className="text-sm text-muted-foreground">Read-only. Recorded in the audit log.</p>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant={tab === "conversations" ? "default" : "outline"}
            onClick={() => setTab("conversations")}>Conversations</Button>
          <Button variant={tab === "discrepancies" ? "default" : "outline"}
            onClick={() => setTab("discrepancies")}>Discrepancies</Button>
        </div>
        {tab === "conversations" && !activeConversation && (
          <ul className="max-h-80 space-y-1 overflow-y-auto text-sm">
            {conversations.map((c) => (
              <li key={c.id}>
                <button className="underline" onClick={() => setActiveConversation(c.id)}>
                  {c.id} - {c.user_id}
                </button>
              </li>
            ))}
            {conversations.length === 0 && <li className="text-muted-foreground">No conversations yet.</li>}
          </ul>
        )}
        {tab === "conversations" && activeConversation && (
          <div className="max-h-80 space-y-2 overflow-y-auto text-sm">
            <button className="text-xs underline" onClick={() => setActiveConversation(null)}>Back to conversations</button>
            {history.map((m, i) => (
              <p key={i}><span className="font-medium">{m.role}:</span> {m.text}</p>
            ))}
          </div>
        )}
        {tab === "discrepancies" && (
          <ul className="max-h-80 space-y-2 overflow-y-auto text-sm">
            {discrepancies.map((d, i) => (
              <li key={i} className="space-y-1">
                <Badge variant="muted">{d.class_label}</Badge>
                <p>{d.summary}</p>
              </li>
            ))}
            {discrepanciesStatus === "loading" && (
              <li className="text-muted-foreground">Loading discrepancies...</li>
            )}
            {discrepanciesStatus === "done" && discrepancies.length === 0 && (
              <li className="text-muted-foreground">No open discrepancies.</li>
            )}
          </ul>
        )}
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </div>
      </div>
    </Dialog>
  );
}
