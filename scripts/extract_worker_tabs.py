"""Move named Worker*Tab exports out of Next.js page.tsx into worker-cockpit-tabs.tsx."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend/apps/creator/app/workers/[id]/page.tsx"
TABS = ROOT / "frontend/apps/creator/components/worker-cockpit-tabs.tsx"

HEADER = '''"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Calendar, ChevronDown, ChevronUp, CircleCheck,
  Copy, Database, ExternalLink, FileText, GraduationCap, HelpCircle, KeyRound, Library, ListChecks,
  Loader2, Lock, Mail, MessageCircle, MessageSquare,
  Phone, Plus, Search, SendHorizonal, Share2, Trash2, Upload, Users, Zap,
  type LucideIcon,
} from "lucide-react";
import { Badge, Button, Card, CardContent, Dialog, Input, Label, Skeleton, cn } from "@qiko/ui";
import { useConfirmActionDialog } from "@/components/confirm-action-dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ChatBubble, TypingIndicator } from "@/components/chat-message";
import { CrmPipeline } from "@/components/crm-pipeline";
import { WorkerVoiceCall } from "@/components/worker-voice-call";
import {
  addFaq, addPolicy, addWebsite, ask, askIntelligence, connectTeamsWebhook, disconnectCalendly, disconnectClickUp,
  disconnectGmail, disconnectSlack,
  deleteDocument, disconnectSalesforce, disconnectTeamsWebhook, financeChat, generateWorkerApiKey,
  getCalendlyCredentials,
  getClickUpCredentials, getFinanceHistory, getGmailCredentials, getIntelligenceChatHistory,
  getSalesforceCredentials, getSlackCredentials,
  getTeamsWebhookStatus, getVapiCredentials, getWorkerApiKeyStatus, ingest, ingestFile, listAgents, listDocuments,
  markReady, revokeWorkerApiKey,
  saveCalendlyCredentials, saveClickUpCredentials, saveGmailCredentials, saveSalesforceCredentials,
  saveSlackCredentials, saveVapiCredentials,
  testCalendlyConnection, testClickUpConnection, testGmailConnection, testSalesforceConnection,
  testSlackConnection, testTeamsWebhook,
  updateAgentConfig, updateCalendlyEventType, type Agent, type Doc,
} from "@/lib/api";
import {
  BEHAVIOR_MAX_CONTENT, BEHAVIOR_MAX_ENTRIES, BEHAVIOR_MAX_TITLE, normalizeBehaviorEntries,
  removeBehaviorEntry, serializeBehaviorEntries, upsertBehaviorEntry, validateBehaviorEntry,
  type BehaviorEntry,
} from "@/lib/behavior-config";

function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn("min-h-24 w-full rounded-lg border border-border bg-muted p-3 text-sm text-slate-700 placeholder:text-slate-500 transition-colors focus-visible:border-indigo-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300", className)} />;
}

'''

PAGE_ONLY = '''"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, BarChart3, Bot, BrainCircuit, ChevronUp, CircleCheck, Database, GraduationCap,
  Link2, Lock, MessageCircle, MessageSquare, Settings, Sparkles, Users, Zap, type LucideIcon,
} from "lucide-react";
import { Badge, Card, CardContent, Skeleton, cn } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { WorkerAvatar } from "@/components/worker-avatar";
import { SourcesTab } from "@/components/sources-tab";
import {
  WorkerChatTab,
  WorkerConnectionsTab,
  WorkerCrmTab,
  WorkerSettingsTab,
  WorkerTrainTab,
} from "@/components/worker-cockpit-tabs";
import { getAgentAnalytics, listAgents, listDocuments, me, type Agent } from "@/lib/api";
import { workerTypeLabel } from "@/lib/stringUtils";

'''


def main() -> None:
    text = PAGE.read_text(encoding="utf-8")
    marker = "export function WorkerCrmTab"
    idx = text.find(marker)
    if idx < 0:
        raise SystemExit("WorkerCrmTab export not found in page.tsx")

    # Keep OverviewTab + AnalyticsTab that sit above WorkerCrmTab
    before = text[:idx]
    # Find start of OverviewTab (after default page component)
    overview = before.find("\nfunction OverviewTab")
    if overview < 0:
        raise SystemExit("OverviewTab not found")
    page_body = before[overview:]  # from OverviewTab through AnalyticsTab
    # Strip any leftover Textarea helper before Overview if present in before... we don't need it
    tabs_body = text[idx:]

    TABS.write_text(HEADER + tabs_body, encoding="utf-8", newline="\n")
    PAGE.write_text(PAGE_ONLY + page_body.lstrip("\n"), encoding="utf-8", newline="\n")

    # Point knowledge imports at worker-cockpit-tabs
    for rel in [
        "frontend/apps/creator/app/knowledge/investors/page.tsx",
        "frontend/apps/creator/app/knowledge/portfolio-reporter/page.tsx",
        "frontend/apps/creator/components/knowledge/investors-chat.tsx",
        "frontend/apps/creator/components/knowledge/portfolio-reporter-chat.tsx",
    ]:
        p = ROOT / rel
        src = p.read_text(encoding="utf-8")
        fixed = src.replace("@/app/workers/[id]/page", "@/components/worker-cockpit-tabs")
        if fixed != src:
            p.write_text(fixed, encoding="utf-8", newline="\n")
            print("FIXED_IMPORT", rel)
        else:
            print("IMPORT_OK", rel)

    exports = [ln for ln in PAGE.read_text(encoding="utf-8").splitlines() if ln.startswith("export ")]
    print("PAGE_EXPORTS", exports)
    print("PAGE_LINES", len(PAGE.read_text(encoding="utf-8").splitlines()))
    print("TABS_LINES", len(TABS.read_text(encoding="utf-8").splitlines()))


if __name__ == "__main__":
    main()
