"use client";

// Notification History -- ported from qiko-frontend origin/idg-sales
// notifications/NotificationHistoryView.tsx, adapted to the V2 cockpit style. A full list of the
// tenant's in-app notifications with an all/unread filter, backed by GET /notifications.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  listNotifications, markAllNotificationsRead, markNotificationRead, type Notification,
} from "@/lib/api";
import { formatDate } from "@/components/sales-intelligence/utils";

const FILTERS = ["all", "unread"] as const;
type Filter = (typeof FILTERS)[number];

function toneClass(type: string): string {
  if (type === "sf_sync_failed" || type === "scan_failed") return "border-red-500/30 bg-red-500/10 text-red-400";
  if (type === "sf_sync_success") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (type === "deadline_reminder") return "border-amber-500/30 bg-amber-500/10 text-amber-400";
  return "border-indigo-500/30 bg-indigo-500/10 text-indigo-400";
}

export function NotificationHistoryView({ category }: { category?: string }) {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");

  const q = useQuery({
    queryKey: ["notifications", category ?? "all", filter],
    queryFn: () => listNotifications({ category, unread_only: filter === "unread", limit: 100 }),
  });
  const notifications: Notification[] = q.data?.notifications ?? [];
  const unread = q.data?.unreadCount ?? 0;

  const invalidate = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const readOne = useMutation({ mutationFn: (id: string) => markNotificationRead(id), onSuccess: invalidate });
  const readAll = useMutation({ mutationFn: () => markAllNotificationsRead(category), onSuccess: invalidate });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-white">
            <Bell className="size-5 text-indigo-400" /> Notifications
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">{unread} unread</p>
        </div>
        {unread > 0 && (
          <button onClick={() => readAll.mutate()} disabled={readAll.isPending}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] font-medium text-slate-200 hover:bg-white/[0.06] disabled:opacity-50">
            <CheckCheck className="size-3.5" /> Mark all read
          </button>
        )}
      </div>

      <div className="flex gap-1 border-b border-white/[0.06]">
        {FILTERS.map((f) => (
          <button key={f} onClick={() => setFilter(f)}
            className={cn("px-3 py-2.5 text-[13px] font-medium capitalize transition-colors",
              filter === f ? "border-b-2 border-indigo-400 text-white" : "text-slate-500 hover:text-slate-300")}>
            {f}
          </button>
        ))}
      </div>

      {q.isLoading ? (
        <p className="text-[13px] text-slate-500">{"Loading\u2026"}</p>
      ) : notifications.length === 0 ? (
        <p className="text-[13px] text-slate-500">No notifications.</p>
      ) : (
        <ul className="space-y-2">
          {notifications.map((n) => (
            <li key={n.id}>
              <button onClick={() => !n.read && readOne.mutate(n.id)}
                className={cn("flex w-full items-start gap-3 rounded-2xl border border-white/[0.06] p-4 text-left transition-colors hover:bg-white/[0.03]",
                  n.read ? "bg-transparent" : "bg-white/[0.02]")}>
                <span className={`inline-flex shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${toneClass(n.type)}`}>
                  {n.type.replace(/_/g, " ")}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={cn("text-[14px]", n.read ? "text-slate-300" : "font-semibold text-white")}>{n.title}</p>
                  {n.body && <p className="mt-0.5 text-[13px] text-slate-500">{n.body}</p>}
                  <p className="mt-1 text-[11px] text-slate-600">{formatDate(n.createdAt, true)}</p>
                </div>
                {!n.read && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-indigo-400" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
