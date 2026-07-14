"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { listAgents } from "@/lib/api";
import { CockpitShell } from "@/components/sales-intelligence/cockpit-shell";
import { NotificationHistoryView } from "@/components/sales-intelligence/notification-history-view";

export default function SalesIntelligenceNotificationsPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const worker = agents.data?.find((a) => a.id === agentId);

  return (
    <CockpitShell agentId={agentId} workerName={worker?.name ?? "IDG - Sales Intelligence"} active="notifications">
      <NotificationHistoryView category="sales_intelligence" />
    </CockpitShell>
  );
}
