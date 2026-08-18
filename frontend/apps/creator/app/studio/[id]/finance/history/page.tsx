"use client";

import { useParams } from "next/navigation";
import { FinanceHistoryPanel } from "@/components/finance/history-panel";

export default function FinanceHistoryPage() {
  const params = useParams<{ id: string }>();
  return (
    <div className="p-4">
      <FinanceHistoryPanel agentId={params.id} />
    </div>
  );
}
