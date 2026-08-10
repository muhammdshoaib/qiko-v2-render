"use client";

/**
 * The activity panel as a drawer, opened from a directory row.
 *
 * The three read-only directories had no detail view at all, so an operator who noticed something odd
 * about a row had nowhere to go: the only way to see what had happened to that user or worker was the
 * global audit page and a hand-typed filter. This is the shortest path from "that looks wrong" to the
 * history that explains it.
 */
import { useRef } from "react";
import { Button, Dialog } from "@qiko/ui";
import { RecentActivity } from "@/components/recent-activity";

export function RowActivityDialog({ open, title, subtitle, targetId, tenantId, note, onClose }: {
  open: boolean;
  title: string;
  subtitle?: string;
  /** Exactly one of these. targetId narrows to the row; tenantId narrows to its whole account. */
  targetId?: string;
  tenantId?: string;
  note?: string;
  onClose: () => void;
}) {
  const opener = useRef<HTMLElement | null>(null);
  if (typeof document !== "undefined" && open && !opener.current) {
    opener.current = document.activeElement as HTMLElement;
  }
  if (!open) opener.current = null;

  return (
    <Dialog open={open} onClose={onClose} opener={opener.current}
      labelledBy="row-activity-title" className="max-w-xl">
      <div className="space-y-4">
        <div>
          <h2 id="row-activity-title" className="text-lg font-semibold">{title}</h2>
          {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {open && (
          <RecentActivity
            scope={targetId ? { targetId } : { tenantId: tenantId! }}
            limit={10}
            note={note}
          />
        )}
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </div>
      </div>
    </Dialog>
  );
}
