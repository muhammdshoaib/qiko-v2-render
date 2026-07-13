"use client";

// CRM / Sales Pipeline tab -- ported 1:1 from the earlier qiko-frontend build
// (client/src/components/dashboard/CRM.tsx) with two real fixes along the way:
// 1. It's wired to the actual backend (app.modules.crm) instead of a client-side mock that
//    hardcoded every contact's status to "contacted" and its summary to "Chat with worker".
// 2. The contact detail view's actions (generate summary, edit contact, mark an action done)
//    were dead stubs (`const generateSummary = () => {}`, called later as `.mutate()`, which
//    would throw) -- these are now real mutations against the new /crm endpoints.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Calendar, Check, CheckCircle2, ChevronRight, Clock, Edit3, Loader2, Mail, MessageSquare,
  Phone, PhoneCall, RefreshCw, Search, Send, Sparkles, User, Users, X, XCircle, Zap,
} from "lucide-react";
import { Badge, Button, Input, cn } from "@qiko/ui";
import {
  addCrmAction, generateCrmSummary, getCrmContact, getCrmPipeline, syncCrmContactToSalesforce,
  updateCrmAction, updateCrmContact, type CrmContact,
} from "@/lib/api";

const PIPELINE_STAGES = [
  { id: "new", label: "New", textColor: "text-blue-400", bgLight: "bg-blue-500/10", border: "border-blue-500/30" },
  { id: "contacted", label: "Contacted", textColor: "text-cyan-400", bgLight: "bg-cyan-500/10", border: "border-cyan-500/30" },
  { id: "interested", label: "Interested", textColor: "text-purple-400", bgLight: "bg-purple-500/10", border: "border-purple-500/30" },
  { id: "quoted", label: "Quoted", textColor: "text-amber-400", bgLight: "bg-amber-500/10", border: "border-amber-500/30" },
  { id: "converted", label: "Converted", textColor: "text-green-400", bgLight: "bg-green-500/10", border: "border-green-500/30" },
  { id: "lost", label: "Lost", textColor: "text-red-400", bgLight: "bg-red-500/10", border: "border-red-500/30" },
] as const;

const STATUS_BADGE: Record<string, string> = {
  new: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  contacted: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25",
  interested: "bg-purple-500/15 text-purple-400 border-purple-500/25",
  quoted: "bg-amber-500/15 text-amber-400 border-amber-500/25",
  converted: "bg-green-500/15 text-green-400 border-green-500/25",
  lost: "bg-red-500/15 text-red-400 border-red-500/25",
};

const SENTIMENT_LABEL: Record<string, { label: string; color: string }> = {
  positive: { label: "Positive", color: "text-green-400" },
  neutral: { label: "Neutral", color: "text-slate-400" },
  negative: { label: "Negative", color: "text-red-400" },
  mixed: { label: "Mixed", color: "text-amber-400" },
};

function timeAgo(date: string | null): string {
  if (!date) return "";
  const diffMs = Date.now() - new Date(date).getTime();
  const mins = Math.floor(diffMs / 60000);
  const hours = Math.floor(diffMs / 3600000);
  const days = Math.floor(diffMs / 86400000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatCurrency(cents: number, currency = "USD") {
  if (!cents) return "";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, minimumFractionDigits: 0 }).format(cents / 100);
}

function PipelineBar({ stats, activeFilter, onFilter }: {
  stats: Record<string, number>; activeFilter: string | null; onFilter: (stage: string | null) => void;
}) {
  return (
    <div className="flex items-stretch gap-1 h-10">
      {PIPELINE_STAGES.map((stage) => {
        const count = stats[stage.id] || 0;
        const isActive = activeFilter === stage.id;
        return (
          <button key={stage.id} onClick={() => onFilter(isActive ? null : stage.id)}
            className={cn("relative flex items-center justify-center gap-1.5 px-3 rounded-md text-xs font-medium transition-all min-w-0",
              count > 0 ? "flex-1" : "flex-none w-auto",
              isActive ? cn(stage.bgLight, stage.textColor, "ring-1 ring-inset", stage.border)
                : count > 0 ? cn(stage.bgLight, stage.textColor) : "bg-white/[0.02] text-slate-600 hover:bg-white/[0.04]")}>
            <span className="font-bold text-sm tabular-nums">{count}</span>
            <span className="hidden sm:inline truncate">{stage.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function ContactRow({ contact, onClick }: { contact: CrmContact; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.03] transition-colors text-left group border-b border-white/[0.04] last:border-b-0">
      <div className="relative shrink-0">
        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary/20 to-cyan-400/20 flex items-center justify-center border border-white/10">
          <span className="text-xs font-semibold text-white/80">{contact.name ? contact.name.charAt(0).toUpperCase() : "?"}</span>
        </div>
        <div className={cn("absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-background",
          PIPELINE_STAGES.find((s) => s.id === contact.status)?.bgLight.replace("/10", "") ?? "bg-slate-500")} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-3.5 h-3.5 shrink-0 text-slate-500" />
          <span className="text-sm font-medium text-white truncate">{contact.name || "Anonymous"}</span>
          {contact.estimatedValue > 0 && (
            <span className="text-[10px] text-green-400/70 font-medium tabular-nums">{formatCurrency(contact.estimatedValue, contact.currency)}</span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-1.5 flex-wrap">
          {contact.email && (
            <span className="flex items-center gap-1.5 text-[11px] text-slate-500 min-w-0">
              <Mail className="w-3 h-3 shrink-0" /><span className="truncate">{contact.email}</span>
            </span>
          )}
          {contact.aiSummary && <span className="text-[11px] text-slate-400 truncate">{contact.aiSummary}</span>}
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-slate-700 group-hover:text-slate-400 transition-colors shrink-0" />
    </button>
  );
}

function ContactDetail({ contactId, onBack }: { contactId: string; onBack: () => void }) {
  const qc = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", email: "", phone: "" });
  const [newAction, setNewAction] = useState("");

  const { data, isLoading } = useQuery({ queryKey: ["crm-contact", contactId], queryFn: () => getCrmContact(contactId) });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["crm-contact", contactId] });
  const updateContact = useMutation({
    mutationFn: (patch: Parameters<typeof updateCrmContact>[1]) => updateCrmContact(contactId, patch),
    onSuccess: invalidate,
  });
  const generateSummary = useMutation({ mutationFn: () => generateCrmSummary(contactId), onSuccess: invalidate });
  const syncSalesforce = useMutation({ mutationFn: () => syncCrmContactToSalesforce(contactId) });
  const addAction = useMutation({
    mutationFn: (title: string) => addCrmAction(contactId, title),
    onSuccess: () => { setNewAction(""); invalidate(); },
  });
  const updateAction = useMutation({
    mutationFn: (vars: { actionId: string; status: string }) => updateCrmAction(vars.actionId, vars.status),
    onSuccess: invalidate,
  });

  if (isLoading) {
    return <div className="flex items-center justify-center h-64"><Loader2 className="w-5 h-5 text-cyan-400 animate-spin" /></div>;
  }
  if (!data) return null;

  const { contact, timeline, actions, stats } = data;
  const pendingActions = actions.filter((a) => a.status === "pending");
  const sentimentInfo = contact.sentiment ? SENTIMENT_LABEL[contact.sentiment] : null;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-white/[0.06]">
        <Button variant="ghost" size="sm" onClick={onBack} className="h-8 w-8 p-0 text-slate-400 hover:text-white">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-white truncate">{contact.name || "Anonymous"}</h2>
            <Badge className={cn("text-[10px]", STATUS_BADGE[contact.status])}>{contact.status}</Badge>
            {sentimentInfo && <span className={cn("text-[10px]", sentimentInfo.color)}>{sentimentInfo.label}</span>}
          </div>
          <p className="text-[11px] text-slate-500 truncate">{[contact.email, contact.phone].filter(Boolean).join(" · ") || "No contact info yet"}</p>
        </div>
        {contact.estimatedValue > 0 && <span className="text-xs font-medium text-green-400 mr-1">{formatCurrency(contact.estimatedValue, contact.currency)}</span>}
        <Button variant="ghost" size="sm" disabled={syncSalesforce.isPending} onClick={() => syncSalesforce.mutate()}
          className="h-7 text-xs text-slate-400 hover:text-white" title="Push this contact to Salesforce as a Lead">
          {syncSalesforce.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
        </Button>
        <Button variant="ghost" size="sm"
          onClick={() => { setEditForm({ name: contact.name || "", email: contact.email || "", phone: contact.phone || "" }); setIsEditing(true); }}
          className="h-7 text-xs text-slate-400 hover:text-white">
          <Edit3 className="w-3 h-3" />
        </Button>
      </div>
      {syncSalesforce.isSuccess && (
        <div className="px-5 py-1.5 bg-emerald-500/10 border-b border-emerald-500/20 text-[11px] text-emerald-400">
          Synced to Salesforce{syncSalesforce.data?.salesforce_id ? ` (Lead ${syncSalesforce.data.salesforce_id})` : ""}.
        </div>
      )}
      {syncSalesforce.isError && (
        <div className="px-5 py-1.5 bg-red-500/10 border-b border-red-500/20 text-[11px] text-red-400">
          Couldn&apos;t sync to Salesforce -- check this worker&apos;s connection in Connections {"\u2192"} Salesforce.
        </div>
      )}

      {isEditing && (
        <div className="px-5 py-2.5 bg-white/[0.03] border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Input placeholder="Name" value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} className="h-7 text-xs flex-1" />
            <Input placeholder="Email" value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} className="h-7 text-xs flex-1" />
            <Input placeholder="Phone" value={editForm.phone} onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })} className="h-7 text-xs flex-1" />
            <Button size="sm" disabled={updateContact.isPending}
              onClick={() => updateContact.mutate({ name: editForm.name || undefined, email: editForm.email || undefined, phone: editForm.phone || undefined },
                { onSuccess: () => setIsEditing(false) })}
              className="h-7 text-xs"><Check className="w-3 h-3" /></Button>
            <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)} className="h-7 text-xs text-slate-400"><X className="w-3 h-3" /></Button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {/* Pipeline stage picker */}
        <div className="flex items-center gap-1.5 px-5 py-3 border-b border-white/[0.04] flex-wrap">
          {PIPELINE_STAGES.map((s) => (
            <button key={s.id} onClick={() => updateContact.mutate({ status: s.id })}
              className={cn("px-2 py-1 rounded-md text-[10px] font-medium transition-colors",
                contact.status === s.id ? cn(s.bgLight, s.textColor) : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]")}>
              {s.label}
            </button>
          ))}
        </div>

        <div className="px-5 py-4 border-b border-white/[0.04]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5"><Sparkles className="w-3.5 h-3.5 text-primary" /><span className="text-xs font-medium text-slate-300">Intent & Summary</span></div>
            <Button variant="ghost" size="sm" onClick={() => generateSummary.mutate()} disabled={generateSummary.isPending} className="h-6 text-[10px] text-slate-500 hover:text-white">
              {generateSummary.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
              {contact.aiSummary ? "Refresh" : "Generate"}
            </Button>
          </div>
          {contact.aiSummary ? (
            <div>
              <p className="text-xs text-slate-300 leading-relaxed">{contact.aiSummary}</p>
              {contact.keyTopics.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {contact.keyTopics.map((topic, i) => (
                    <span key={i} className="px-1.5 py-0.5 rounded text-[10px] bg-primary/10 text-primary/80">{topic}</span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-[11px] text-slate-500 italic">Click &quot;Generate&quot; to analyze the conversation and surface this contact&apos;s intent.</p>
          )}
          {generateSummary.isError && <p className="text-[11px] text-red-400 mt-1">Couldn&apos;t generate a summary -- try again in a moment.</p>}
        </div>

        <div className="flex items-center gap-4 px-5 py-2.5 border-b border-white/[0.04] text-[11px] text-slate-500">
          <span className="flex items-center gap-1"><MessageSquare className="w-3 h-3" />{stats.messageCount} chats</span>
          <span className="flex items-center gap-1"><PhoneCall className="w-3 h-3" />{stats.voiceCallCount} calls</span>
          <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{stats.emailCount} emails</span>
        </div>

        <div className="px-5 py-3 border-b border-white/[0.04]">
          <div className="flex items-center gap-1.5 mb-2">
            <Zap className="w-3.5 h-3.5 text-amber-400" /><span className="text-xs font-medium text-slate-300">Next Actions</span>
            {pendingActions.length > 0 && <span className="text-[10px] text-slate-500">({pendingActions.length})</span>}
          </div>
          <div className="space-y-1.5 mb-2">
            {pendingActions.map((action) => (
              <div key={action.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06] group hover:border-white/10 transition-colors">
                <span className="text-xs text-white flex-1 truncate">{action.title}</span>
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={() => updateAction.mutate({ actionId: action.id, status: "done" })} className="p-1 rounded hover:bg-green-500/10 text-green-400" title="Done">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => updateAction.mutate({ actionId: action.id, status: "dismissed" })} className="p-1 rounded hover:bg-white/5 text-slate-500" title="Dismiss">
                    <XCircle className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
            {pendingActions.length === 0 && <p className="text-[11px] text-slate-500 italic">No open actions.</p>}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); if (newAction.trim()) addAction.mutate(newAction.trim()); }} className="flex gap-1.5">
            <Input value={newAction} onChange={(e) => setNewAction(e.target.value)} placeholder="Add a follow-up action…" className="h-7 text-xs flex-1" />
            <Button type="submit" size="sm" disabled={!newAction.trim() || addAction.isPending} className="h-7 text-xs">Add</Button>
          </form>
        </div>

        <div className="px-5 py-3">
          <div className="flex items-center gap-1.5 mb-3">
            <Clock className="w-3.5 h-3.5 text-slate-400" /><span className="text-xs font-medium text-slate-300">What Happened</span>
            <span className="text-[10px] text-slate-500">({timeline.length} events)</span>
          </div>
          {timeline.length === 0 ? (
            <div className="text-center py-6"><Clock className="w-6 h-6 text-slate-700 mx-auto mb-1.5" /><p className="text-xs text-slate-500">No interactions recorded yet</p></div>
          ) : (
            <div className="relative">
              <div className="absolute left-[15px] top-2 bottom-2 w-px bg-white/[0.06]" />
              <div className="space-y-0.5">
                {timeline.map((event, i) => (
                  <div key={i} className="flex gap-3 py-2 relative">
                    <div className="w-[30px] h-[30px] rounded-full flex items-center justify-center shrink-0 bg-background border border-white/[0.08] z-10 text-cyan-400">
                      <MessageSquare className="w-3.5 h-3.5" />
                    </div>
                    <div className="flex-1 min-w-0 pt-0.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-white">{event.title}</span>
                        <span className="text-[10px] text-slate-600">{timeAgo(event.timestamp)}</span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5 line-clamp-2">{event.summary}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function CrmPipeline({ agentId }: { agentId: string }) {
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [stageFilter, setStageFilter] = useState<string | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["crm-pipeline", agentId], queryFn: () => getCrmPipeline(agentId) });

  if (selectedContactId) {
    return <ContactDetail contactId={selectedContactId} onBack={() => setSelectedContactId(null)} />;
  }

  const contacts = data?.contacts ?? [];
  const searchLower = searchQuery.trim().toLowerCase();
  const filtered = contacts.filter((c) => {
    if (stageFilter && c.status !== stageFilter) return false;
    if (!searchLower) return true;
    return [c.name, c.email, c.phone].some((v) => (v ?? "").toLowerCase().includes(searchLower));
  });
  const totalValue = filtered.reduce((sum, c) => sum + c.estimatedValue, 0);

  return (
    <div className="h-full flex flex-col overflow-hidden rounded-lg border border-border">
      <div className="px-5 pt-3 pb-3 border-b border-white/[0.06]">
        <h2 className="text-sm font-semibold text-white">Sales Pipeline</h2>
        <p className="text-[11px] text-slate-500 mt-0.5">
          {filtered.length} contact{filtered.length !== 1 ? "s" : ""}{totalValue > 0 ? ` · ${formatCurrency(totalValue)} pipeline value` : ""}
        </p>
        <div className="mt-3">
          <PipelineBar stats={data?.dashboard.statusBreakdown ?? {}} activeFilter={stageFilter} onFilter={setStageFilter} />
        </div>
        <div className="relative mt-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
          <Input placeholder="Search by name, email, or phone…" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-8 text-xs placeholder:text-slate-600" />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-5 space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 animate-pulse">
                <div className="w-9 h-9 rounded-full bg-white/5" />
                <div className="flex-1"><div className="h-3.5 bg-white/5 rounded w-28 mb-1.5" /><div className="h-3 bg-white/[0.03] rounded w-48" /></div>
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6 py-12">
            <Users className="w-10 h-10 text-slate-700 mb-2" />
            <h3 className="text-sm font-medium text-slate-400 mb-1">
              {searchQuery.trim() ? "No contacts match your search" : stageFilter ? `No ${stageFilter} contacts` : "No contacts yet"}
            </h3>
            <p className="text-[11px] text-slate-600 max-w-xs">
              {searchQuery.trim() || stageFilter ? "Try a different search or filter." : "Contacts appear here automatically once a prospect chats with this worker."}
            </p>
          </div>
        ) : (
          <div>
            <div className="flex items-center gap-3 px-4 py-1.5 text-[10px] text-slate-600 uppercase tracking-wider border-b border-white/[0.04]">
              <div className="w-9" /><div className="flex-1">Contact / Last Interaction</div><div className="w-4" />
            </div>
            {filtered.map((contact) => (
              <ContactRow key={contact.id} contact={contact} onClick={() => setSelectedContactId(contact.id)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
