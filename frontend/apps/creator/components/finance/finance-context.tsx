"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getFinanceAnalytics, listAgents, listFinanceFiles, type FinanceAnalytics, type FinanceFile } from "@/lib/api";

interface FinanceContextValue {
  agentId: string;
  workerName: string;
  analytics: FinanceAnalytics | undefined;
  isLoading: boolean;
  files: FinanceFile[] | undefined;
  filesLoading: boolean;
  month: string;
  setMonth: (value: string) => void;
  chatOpen: boolean;
  setChatOpen: React.Dispatch<React.SetStateAction<boolean>>;
  filesOpen: boolean;
  setFilesOpen: React.Dispatch<React.SetStateAction<boolean>>;
}

const FinanceContext = createContext<FinanceContextValue | null>(null);

export function FinanceProvider({ agentId, children }: { agentId: string; children: React.ReactNode }) {
  const [month, setMonth] = useState<string>("all");
  const [chatOpen, setChatOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);

  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const workerName = useMemo(() => agents.data?.find((a) => a.id === agentId)?.name ?? "Financial Analyst", [agents.data, agentId]);

  const analyticsQ = useQuery({
    queryKey: ["finance-analytics", agentId, month],
    queryFn: () => getFinanceAnalytics(agentId, month !== "all" ? { month } : {}),
    retry: false,
  });

  const filesQ = useQuery({
    queryKey: ["finance-files", agentId],
    queryFn: () => listFinanceFiles(agentId),
    retry: false,
  });

  const value = useMemo(() => ({
    agentId,
    workerName,
    analytics: analyticsQ.data,
    isLoading: analyticsQ.isLoading,
    files: filesQ.data?.files,
    filesLoading: filesQ.isLoading,
    month,
    setMonth,
    chatOpen,
    setChatOpen,
    filesOpen,
    setFilesOpen,
  }), [agentId, workerName, analyticsQ.data, analyticsQ.isLoading, filesQ.data, filesQ.isLoading, month, chatOpen, filesOpen]);

  return <FinanceContext.Provider value={value}>{children}</FinanceContext.Provider>;
}

export function useFinance() {
  const ctx = useContext(FinanceContext);
  if (!ctx) throw new Error("useFinance must be used inside a FinanceProvider");
  return ctx;
}
