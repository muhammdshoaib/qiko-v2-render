"use client";

import { useParams } from "next/navigation";
import { FinanceHistoryPanel } from "@/components/finance/history-panel";

export default function FinanceHistoryPage() {
  const params = useParams<{ id: string }>();
  return (
    <div className="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden p-4">
      <FinanceHistoryPanel agentId={params.id} />
    </div>
  );
}
