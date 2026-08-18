"use client";

import { useParams } from "next/navigation";
import { FinanceShell } from "@/components/finance/finance-shell";

export default function FinanceLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id: string }>();
  return <FinanceShell agentId={params.id}>{children}</FinanceShell>;
}
