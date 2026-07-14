"use client";

// In-app notification bell + dropdown panel -- ported from qiko-frontend origin/idg-sales
// notifications/{NotificationBell,NotificationPanel,NotificationItem}.tsx, adapted to the V2
// cockpit style. Polls the generic tenant-scoped inbox (/notifications) and lets the user mark
// items read / read-all. In-product only (no email/FCM push).
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { cn } from "@qiko/ui";
import {
  listNotifications, markAllNotificationsRead, markNotificationRead, type Notification,
} from "@/lib/api";
import { formatDate } from "@/components/sales-intelligence/utils";

const NOTIFICATIONS_QUERY_KEY = ["notifications"] as const;

function toneClass(type: string): string {
  if (type === "sf_sync_failed" || type === "scan_failed") return "bg-red-400";
  if (type === "sf_sync_success") return "bg-emerald-400";
  if (type === "deadline_reminder") return "bg-amber-400";
  return "bg-indigo-400";
}

function NotificationItem({ n, onRead }: { n: Notification; onRead: (id: string) => void }) {
  return (
    <button onClick={() => !n.read && onRead(n.id)}
      className={cn("flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-white/[0.04]",
        !n.read && "bg-white/[0.02]")}>
      <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", n.read ? "bg-transparent" : toneClass(n.type))} />
      <div className="min-w-0 flex-1">
        <p className={cn("truncate text-[13px]", n.read ? "text-slate-400" : "font-semibold text-white")}>{n.title}</p>
        {n.body && <p className="mt-0.5 line-clamp-2 text-[12px] text-slate-500">{n.body}</p>}
        <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-600">{formatDate(n.createdAt, true)}</p>
      </div>
    </button>
  );
}

export function NotificationBell({ category }: { category?: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const q = useQuery({
    queryKey: [...NOTIFICATIONS_QUERY_KEY, category ?? "all"],
    queryFn: () => listNotifications({ category, limit: 50 }),
    refetchInterval: 30_000,
  });
  const notifications: Notification[] = q.data?.notifications ?? [];
  const unread = q.data?.unreadCount ?? 0;

  const invalidate = () => qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
  const readOne = useMutation({ mutationFn: (id: string) => markNotificationRead(id), onSuccess: invalidate });
  const readAll = useMutation({ mutationFn: () => markAllNotificationsRead(category), onSuccess: invalidate });

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((v) => !v)} aria-label="Notifications" aria-expanded={open}
        className="relative flex size-8 items-center justify-center rounded-lg text-slate-400 hover:bg-white/[0.06] hover:text-white">
        <Bell className="size-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-indigo-500 px-1 text-[9px] font-bold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 z-50 w-[340px] max-w-[90vw] rounded-2xl border border-white/[0.08] bg-[#0a0f1a] shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
            <p className="text-[13px] font-semibold text-white">Notifications</p>
            {unread > 0 && (
              <button onClick={() => readAll.mutate()} disabled={readAll.isPending}
                className="flex items-center gap-1 text-[11px] font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50">
                <CheckCheck className="size-3.5" /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-[400px] space-y-0.5 overflow-y-auto p-2">
            {q.isLoading ? (
              <p className="px-3 py-6 text-center text-[13px] text-slate-500">{"Loading\u2026"}</p>
            ) : notifications.length === 0 ? (
              <p className="px-3 py-6 text-center text-[13px] text-slate-500">You&apos;re all caught up.</p>
            ) : (
              notifications.map((n) => <NotificationItem key={n.id} n={n} onRead={readOne.mutate} />)
            )}
          </div>
        </div>
      )}
    </div>
  );
}
