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

  if (typeof document !== "undefined" && open && !opener.current) {
    opener.current = document.activeElement as HTMLElement;
  }
  if (!open) opener.current = null;

  return (
    <Dialog open={open} onClose={onClose} opener={opener.current}
      labelledBy="worker-support-title" className="max-w-2xl">
      {open && <SupportContent key={agentId} agentId={agentId} workerName={workerName} onClose={onClose} />}
    </Dialog>
  );
}

function SupportContent({ agentId, workerName, onClose }: {
  agentId: string;
  workerName: string;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("conversations");
  const [conversations, setConversations] = useState<SupportConversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [history, setHistory] = useState<SupportMessage[]>([]);
  const [discrepancies, setDiscrepancies] = useState<SupportDiscrepancy[]>([]);
  const [discrepanciesTotal, setDiscrepanciesTotal] = useState(0);
  const [hasDiscrepanciesResult, setHasDiscrepanciesResult] = useState(false);
  const [discrepanciesStatus, setDiscrepanciesStatus] = useState<"idle" | "loading" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(false);
  const loadedDiscrepancies = useRef(false);
  const historyRequestId = useRef(0);

  function selectConversation(id: string | null) {
    historyRequestId.current += 1;
    setHistory([]);
    setActiveConversation(id);
  }

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    getSupportWorker(agentId)
      .then(() => {
        if (!mounted.current) return;
        listSupportConversations(agentId)
          .then((items) => { if (mounted.current) setConversations(items); })
          .catch(() => { if (mounted.current) setError("Could not load conversations."); });
      })
      .catch(() => { if (mounted.current) setError("This worker no longer has a support view."); });
  }, [agentId]);

  useEffect(() => {
    if (!activeConversation) { setHistory([]); return; }
    setHistory([]);
    const requestId = ++historyRequestId.current;
    let current = true;
    getSupportConversationHistory(agentId, activeConversation)
      .then((items) => { if (current && historyRequestId.current === requestId) setHistory(items); })
      .catch(() => { if (current && historyRequestId.current === requestId) setError("Could not load that conversation."); });
    return () => { current = false; };
  }, [agentId, activeConversation]);

  useEffect(() => {
    if (tab !== "discrepancies" || loadedDiscrepancies.current) return;
    loadedDiscrepancies.current = true;
    setDiscrepanciesStatus("loading");
    listSupportDiscrepancies(agentId, 50, 0)
      .then((body) => {
        if (!mounted.current) return;
        setDiscrepancies(body.items);
        setDiscrepanciesTotal(body.total);
        setHasDiscrepanciesResult(true);
        setDiscrepanciesStatus("done");
      })
      .catch(() => {
        if (!mounted.current) return;
        setError("Could not load discrepancies.");
        setDiscrepanciesStatus("done");
      });
  }, [tab, agentId]);

  async function loadMore() {
    if (discrepanciesStatus !== "done" || discrepancies.length >= discrepanciesTotal) return;
    setError(null);
    setDiscrepanciesStatus("loading");
    try {
      const body = await listSupportDiscrepancies(agentId, 50, discrepancies.length);
      if (!mounted.current) return;
      setDiscrepancies((items) => [...items, ...body.items]);
      setDiscrepanciesTotal(body.total);
    } catch {
      if (mounted.current) setError("Could not load more discrepancies.");
    } finally {
      if (mounted.current) setDiscrepanciesStatus("done");
    }
  }

  return (
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
                <button className="underline" onClick={() => selectConversation(c.id)}>
                  {c.id} - {c.user_id}
                </button>
              </li>
            ))}
            {conversations.length === 0 && <li className="text-muted-foreground">No conversations yet.</li>}
          </ul>
        )}
        {tab === "conversations" && activeConversation && (
          <div className="max-h-80 space-y-2 overflow-y-auto text-sm">
            <button className="text-xs underline" onClick={() => selectConversation(null)}>Back to conversations</button>
            {history.map((m, i) => (
              <p key={i}><span className="font-medium">{m.role}:</span> {m.text}</p>
            ))}
          </div>
        )}
        {tab === "discrepancies" && (
          <div className="space-y-2">
          {hasDiscrepanciesResult && (
            <p className="text-sm text-muted-foreground">Showing {discrepancies.length ? `1–${discrepancies.length}` : "0"} of {discrepanciesTotal}</p>
          )}
          <ul className="max-h-80 space-y-2 overflow-y-auto text-sm">
            {discrepancies.map((d, i) => (
              <li key={i} className="space-y-1">
                <Badge variant="muted">{d.class_label}</Badge>
                <p>{d.summary}</p>
              </li>
            ))}
            {discrepanciesStatus === "loading" && discrepancies.length === 0 && (
              <li className="text-muted-foreground">Loading discrepancies...</li>
            )}
            {discrepanciesStatus === "done" && discrepancies.length === 0 && !error && (
              <li className="text-muted-foreground">No open discrepancies.</li>
            )}
          </ul>
          {discrepanciesStatus === "done" && discrepancies.length < discrepanciesTotal && (
            <Button variant="outline" onClick={loadMore}>Load more</Button>
          )}
          {discrepanciesStatus === "loading" && discrepancies.length > 0 && (
            <p className="text-sm text-muted-foreground">Loading more...</p>
          )}
          </div>
        )}
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </div>
      </div>
  );
}
